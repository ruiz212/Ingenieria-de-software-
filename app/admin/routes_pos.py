from decimal import Decimal, InvalidOperation
from app.services.validation import amount, positive_int
from app.services.currency import official_usd_rate
# app/admin/routes_pos.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback
import pyodbc

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

DENOMINACIONES_VALIDAS = {
    'NIO': {
        Decimal('1000.00'), Decimal('500.00'), Decimal('200.00'), Decimal('100.00'),
        Decimal('50.00'), Decimal('20.00'), Decimal('10.00'), Decimal('5.00'),
        Decimal('1.00'), Decimal('0.50'), Decimal('0.25'), Decimal('0.10'), Decimal('0.05'),
    },
    'USD': {
        Decimal('100.00'), Decimal('50.00'), Decimal('20.00'), Decimal('10.00'),
        Decimal('5.00'), Decimal('2.00'), Decimal('1.00'),
        Decimal('0.50'), Decimal('0.25'), Decimal('0.10'), Decimal('0.05'), Decimal('0.01'),
    },
}


def _validar_denominaciones_arqueo(denominaciones, efectivo_declarado, efectivo_explicit, dolares_declarados, dolares_explicit):
    """Valida el desglose de denominaciones en servidor y exige congruencia con los montos declarados."""
    if denominaciones is None:
        return [], efectivo_declarado, dolares_declarados
    if not isinstance(denominaciones, list):
        raise ValueError('El desglose de denominaciones debe ser una lista.')
    if len(denominaciones) == 0:
        return [], efectivo_declarado, dolares_declarados

    validadas = []
    total_nio = Decimal('0.00')
    total_usd = Decimal('0.00')
    tiene_nio = False
    tiene_usd = False

    for item in denominaciones:
        if not isinstance(item, dict):
            raise ValueError('Cada elemento de denominación debe ser un objeto válido.')
        tipo = str(item.get('tipo', 'NIO')).strip().upper()
        if tipo not in DENOMINACIONES_VALIDAS:
            raise ValueError(f'Moneda de denominación inválida: {tipo}.')
        denom = amount(item.get('denominacion'), 'Denominación', minimum=Decimal('0.01'))
        if denom not in DENOMINACIONES_VALIDAS[tipo]:
            raise ValueError(f'Denominación inexistente ({denom}) para moneda {tipo}.')

        raw_cant = item.get('cantidad', 0)
        if isinstance(raw_cant, bool) or raw_cant is None or raw_cant == '':
            raise ValueError('La cantidad de denominación debe ser un número entero.')
        try:
            dec_cant = Decimal(str(raw_cant))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError('La cantidad de denominación debe ser un número entero.') from exc
        if not dec_cant.is_finite() or dec_cant != int(dec_cant) or int(dec_cant) < 0 or int(dec_cant) > 1_000_000:
            raise ValueError('La cantidad de denominación debe ser un entero no negativo.')
        cantidad = int(dec_cant)

        subtotal = amount(denom * cantidad)
        if tipo == 'NIO':
            tiene_nio = True
            total_nio = amount(total_nio + subtotal)
        else:
            tiene_usd = True
            total_usd = amount(total_usd + subtotal)
        validadas.append({'tipo': tipo, 'denominacion': denom, 'cantidad': cantidad, 'subtotal': subtotal})

    if tiene_nio or not tiene_usd:
        if efectivo_explicit and abs(efectivo_declarado - total_nio) > Decimal('0.01'):
            raise ValueError(
                f'Incongruencia entre el efectivo declarado (C${efectivo_declarado:.2f}) '
                f'y el desglose de denominaciones (C${total_nio:.2f}).'
            )
        efectivo_declarado = total_nio
    elif efectivo_explicit and efectivo_declarado > Decimal('0.00'):
        raise ValueError(
            f'Incongruencia entre el efectivo declarado (C${efectivo_declarado:.2f}) y el desglose sin denominaciones NIO.'
        )

    if tiene_usd:
        if dolares_explicit and abs(dolares_declarados - total_usd) > Decimal('0.01'):
            raise ValueError(
                f'Incongruencia entre los dólares declarados (${dolares_declarados:.2f}) '
                f'y el desglose de denominaciones USD (${total_usd:.2f}).'
            )
        dolares_declarados = total_usd

    return validadas, efectivo_declarado, dolares_declarados

@admin_bp.route('/arqueos')
@login_required
@roles_required('Admin', 'SuperAdmin')
def arqueos():
    """Módulo de Arqueos de Caja — Vista principal con historial."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Arqueos recientes con detalles
    execute_sp(
        cursor,
        'ventas.sp_ListarArqueosAdmin',
        fallback_sql="""
        SELECT TOP 50 a.ID, a.TurnoID, u_cajero.NombreCompleto AS Cajero,
               ISNULL(u_verif.NombreCompleto, '—') AS Verificador,
               a.EfectivoContado, a.EfectivoSistema,
               a.TransferenciasContadas, a.TransferenciasSistema,
               a.DiferenciaEfectivo, a.DiferenciaTransferencias,
               a.DolaresContados, a.TipoCambioUsado,
               a.Observaciones, a.NotasDiscrepancia,
               ISNULL(a.EstadoArqueo, 'Cerrado') AS EstadoArqueo,
               a.FechaArqueo, a.FechaVerificacion,
               ISNULL(a.RequiereJustificacion, 0) AS RequiereJustificacion
        FROM ArqueoCaja a
        JOIN Usuarios u_cajero ON a.UsuarioID = u_cajero.ID
        LEFT JOIN Usuarios u_verif ON a.VerificadoPorID = u_verif.ID
        ORDER BY a.FechaArqueo DESC
    """,
    )
    arqueos_list = []
    for r in cursor.fetchall():
        dif_total = float(r.DiferenciaEfectivo) + float(r.DiferenciaTransferencias)
        arqueos_list.append({
            'id': r.ID,
            'turno_id': r.TurnoID,
            'cajero': r.Cajero,
            'verificador': r.Verificador,
            'efectivo_contado': float(r.EfectivoContado),
            'efectivo_sistema': float(r.EfectivoSistema),
            'transferencias_contadas': float(r.TransferenciasContadas),
            'transferencias_sistema': float(r.TransferenciasSistema),
            'dif_efectivo': float(r.DiferenciaEfectivo),
            'dif_transferencias': float(r.DiferenciaTransferencias),
            'dif_total': dif_total,
            'dolares_contados': float(r.DolaresContados),
            'tipo_cambio': float(r.TipoCambioUsado) if r.TipoCambioUsado else 0,
            'observaciones': r.Observaciones or '',
            'notas_discrepancia': r.NotasDiscrepancia or '',
            'estado': r.EstadoArqueo,
            'fecha': r.FechaArqueo.strftime('%d/%m/%Y %H:%M'),
            'fecha_verificacion': r.FechaVerificacion.strftime('%d/%m/%Y %H:%M') if r.FechaVerificacion else '',
            'requiere_justificacion': bool(r.RequiereJustificacion),
        })

    # Turnos abiertos (para poder iniciar arqueo desde aquí)
    execute_sp(
        cursor,
        'ventas.sp_DashboardTurnosActivos',
        fallback_sql="""
        SELECT t.ID, u.NombreCompleto, t.FechaApertura
        FROM TurnosCaja t
        JOIN Usuarios u ON t.UsuarioID = u.ID
        WHERE t.Cerrado = 0
    """,
    )
    turnos_abiertos = [{'id': r.ID, 'usuario': r.NombreCompleto, 'apertura': r.FechaApertura.strftime('%H:%M:%S')} for r in cursor.fetchall()]

    # Umbral de discrepancia
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerConfiguracionClave',
        ('umbral_discrepancia_cordobas',),
        fallback_sql="SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'umbral_discrepancia_cordobas'",
        fallback_params=(),
    )
    row = cursor.fetchone()
    umbral = float(row.Valor) if row else 50.0

    # Estadísticas resumen
    execute_sp(
        cursor,
        'ventas.sp_EstadisticasResumenArqueos',
        fallback_sql="""
        SELECT
            COUNT(*) AS Total,
            SUM(CASE WHEN ABS(DiferenciaEfectivo) + ABS(DiferenciaTransferencias) < 1 THEN 1 ELSE 0 END) AS Cuadrados,
            SUM(CASE WHEN DiferenciaEfectivo > 0 THEN 1 ELSE 0 END) AS Sobrantes,
            SUM(CASE WHEN DiferenciaEfectivo < 0 THEN 1 ELSE 0 END) AS Faltantes,
            ISNULL(AVG(ABS(DiferenciaEfectivo)), 0) AS PromDiferencia
        FROM ArqueoCaja
        WHERE FechaArqueo >= DATEADD(DAY, -30, GETDATE())
    """,
    )
    stats_row = cursor.fetchone()
    estadisticas = {
        'total': stats_row.Total,
        'cuadrados': stats_row.Cuadrados,
        'sobrantes': stats_row.Sobrantes,
        'faltantes': stats_row.Faltantes,
        'promedio_diferencia': round(float(stats_row.PromDiferencia), 2)
    }

    conn.close()
    return render_template('admin/arqueos.html', user=current_user,
        arqueos=arqueos_list, turnos_abiertos=turnos_abiertos,
        umbral=umbral, estadisticas=estadisticas)


@admin_bp.route('/api/arqueo/etapa1-conteo', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def arqueo_etapa1_conteo():
    """Etapa 1: Cajero envía conteo desglosado por denominación.

    Nota contable (L13): El arqueo de turno POS concilia exclusivamente la gaveta
    operativa del turno (ventas en efectivo, adelantos, liquidaciones de saldo y
    devoluciones/anulaciones en efectivo atribuidas a TurnoReceptorID en ventas.Pagos).
    Los egresos privados (contabilidad.EgresosPrivados) y vales (rrhh.ValesEmpleados)
    se desembolsan desde Caja General de oficina (1.1.01.001) y no desde la gaveta POS.
    """
    datos = request.json or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        efectivo_explicit = 'efectivo_contado' in datos and datos.get('efectivo_contado') not in (None, '')
        dolares_explicit = 'dolares_contados' in datos and datos.get('dolares_contados') not in (None, '')
        efectivo_contado = amount(datos.get('efectivo_contado', 0) if efectivo_explicit else 0)
        transferencias_contadas = amount(datos.get('transferencias_contadas', 0) if datos.get('transferencias_contadas') not in (None, '') else 0)
        dolares_contados = amount(datos.get('dolares_contados', 0) if dolares_explicit else 0)
        observaciones = datos.get('observaciones', '')
        denominaciones, efectivo_contado, dolares_contados = _validar_denominaciones_arqueo(
            datos.get('denominaciones', []),
            efectivo_contado,
            efectivo_explicit,
            dolares_contados,
            dolares_explicit,
        )

        # Buscar turno activo del usuario
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTurnoActivoParaVenta',
            (current_user.id,),
            fallback_sql="SELECT ID FROM TurnosCaja WITH(UPDLOCK,HOLDLOCK) WHERE UsuarioID = ? AND Cerrado = 0",
        )
        turno_row = cursor.fetchone()
        if not turno_row:
            return jsonify({'error': 'No tienes un turno activo para cerrar'}), 400

        turno_id = turno_row.ID
        execute_sp(
            cursor,
            'ventas.sp_VerificarArqueoPendienteTurno',
            (turno_id,),
            fallback_sql="SELECT ID FROM ArqueoCaja WHERE TurnoID=? AND EstadoArqueo IN ('Pendiente','Verificado')",
        )
        if cursor.fetchone():
            return jsonify(error='Ya existe un arqueo pendiente para este turno.'), 409

        # Calcular valores del sistema de la gaveta del turno POS (incluye cobros y resta devoluciones/anulaciones del turno)
        execute_sp(
            cursor,
            'ventas.sp_CalcularValoresSistemaTurno',
            (turno_id,),
            fallback_sql="""
            SELECT
                ISNULL(SUM(CASE WHEN (p.MetodoPago = 'Efectivo' OR (p.MetodoPago='Efectivo USD' AND p.MonedaRegistro='NIO')) THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' AND p.MonedaRegistro<>'NIO' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
            FROM Pagos p
            WHERE p.TurnoReceptorID = ?
        """,
        )
        row = cursor.fetchone()

        efectivo_cordobas = amount(row.EfectivoCordobasSistema)
        efectivo_usd_sistema = amount(row.EfectivoUSDSistema)
        transferencias_sistema = amount(row.TransferenciasSistema)

        tipo_cambio = official_usd_rate(cursor)

        # Convertir USD del sistema a córdobas
        efectivo_sistema = amount(efectivo_cordobas + efectivo_usd_sistema * tipo_cambio)

        # Total contado incluyendo dólares convertidos
        dolares_en_cordobas = amount(dolares_contados * tipo_cambio)
        efectivo_total_contado = amount(efectivo_contado + dolares_en_cordobas)

        # Diferencias
        dif_efectivo = efectivo_total_contado - efectivo_sistema
        dif_transferencias = transferencias_contadas - transferencias_sistema

        # Determinar si requiere justificación
        execute_sp(
            cursor,
            'seguridad.sp_ObtenerConfiguracionClave',
            ('umbral_discrepancia_cordobas',),
            fallback_sql="SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'umbral_discrepancia_cordobas'",
            fallback_params=(),
        )
        umbral_row = cursor.fetchone()
        umbral = amount(umbral_row.Valor if umbral_row else 50)
        requiere_justificacion = abs(dif_efectivo) >= umbral or abs(dif_transferencias) >= umbral

        # Total ventas del turno
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTotalVentasEmitidasTurno',
            (turno_id,),
            fallback_sql="SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE EstadoFiscal='Emitida' AND TurnoID = ?",
        )
        total_ventas = float(cursor.fetchone()[0])

        # Insertar arqueo en estado Pendiente
        execute_sp(
            cursor,
            'ventas.sp_InsertarArqueoEtapa1',
            (
                turno_id, current_user.id, efectivo_total_contado, transferencias_contadas,
                dolares_contados, tipo_cambio if tipo_cambio > 0 else None,
                efectivo_sistema, transferencias_sistema,
                dif_efectivo, dif_transferencias, observaciones,
                1 if requiere_justificacion else 0
            ),
            fallback_sql="""
            INSERT INTO ArqueoCaja (TurnoID, UsuarioID, EfectivoContado, TransferenciasContadas,
                DolaresContados, TipoCambioUsado, EfectivoSistema, TransferenciasSistema,
                DiferenciaEfectivo, DiferenciaTransferencias, Observaciones,
                EstadoArqueo, RequiereJustificacion)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
        """,
        )

        arqueo_id = cursor.fetchone()[0]

        # Insertar detalle por denominación validada
        for d in denominaciones:
            if d['cantidad'] > 0:
                execute_sp(
                    cursor,
                    'ventas.sp_InsertarArqueoDenominacion',
                    (arqueo_id, d['tipo'], float(d['denominacion']), int(d['cantidad'])),
                    fallback_sql="""
                    INSERT INTO ArqueoDetalleDenominacion (ArqueoID, TipoMoneda, Denominacion, Cantidad)
                    VALUES (?, ?, ?, ?)
                """,
                )

        # Audit log
        execute_sp(
            cursor,
            'ventas.sp_InsertarArqueoAuditLog',
            (
                arqueo_id, current_user.id, 'CONTEO_REGISTRADO',
                f'Efectivo contado: C${efectivo_total_contado:.2f} | Sistema: C${efectivo_sistema:.2f} | Dif: C${dif_efectivo:.2f}',
                request.remote_addr
            ),
            fallback_sql="""
            INSERT INTO ArqueoAuditLog (ArqueoID, UsuarioID, Accion, Detalle, DireccionIP)
            VALUES (?, ?, 'CONTEO_REGISTRADO', ?, ?)
        """,
            fallback_params=(
                arqueo_id, current_user.id,
                f'Efectivo contado: C${efectivo_total_contado:.2f} | Sistema: C${efectivo_sistema:.2f} | Dif: C${dif_efectivo:.2f}',
                request.remote_addr
            ),
        )

        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Conteo registrado. Pendiente de verificación de gerencia.',
            'arqueo_id': arqueo_id,
            'arqueo': {
                'efectivo_sistema': float(efectivo_sistema),
                'transferencias_sistema': float(transferencias_sistema),
                'efectivo_contado': float(efectivo_total_contado),
                'transferencias_contadas': float(transferencias_contadas),
                'diferencia_efectivo': float(dif_efectivo),
                'diferencia_transferencias': float(dif_transferencias),
                'tipo_cambio_aplicado': float(tipo_cambio),
                'total_ventas': total_ventas,
                'requiere_justificacion': requiere_justificacion,
                'origen_efectivo_sistema': 'gaveta_turno_pos',
                'egresos_caja_general_excluidos': True
            }
        })
    except ValueError as error:
        conn.rollback()
        return jsonify(error=str(error)), 400
    except pyodbc.Error as error:
        conn.rollback()
        if '51021' in str(error):
            return jsonify(error='Existen movimientos históricos sin receptor de caja. Admin debe conciliar los recibos antes del arqueo.'), 409
        raise
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/arqueo/<int:arqueo_id>/verificar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def arqueo_etapa2_verificar(arqueo_id):
    """Etapa 2: Supervisor verifica y firma el conteo."""
    datos = request.json
    notas_discrepancia = datos.get('notas_discrepancia', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Obtener el arqueo
        execute_sp(
            cursor,
            'ventas.sp_ObtenerArqueoParaVerificarBloqueo',
            (arqueo_id,),
            fallback_sql="SELECT UsuarioID, RequiereJustificacion, EstadoArqueo FROM ArqueoCaja WITH(UPDLOCK,HOLDLOCK) WHERE ID = ?",
        )
        arqueo = cursor.fetchone()
        if not arqueo:
            return jsonify({'error': 'Arqueo no encontrado'}), 404

        if arqueo.EstadoArqueo != 'Pendiente':
            return jsonify({'error': 'Este arqueo ya fue verificado'}), 400

        # El verificador debe ser diferente al cajero
        if arqueo.UsuarioID == current_user.id:
            return jsonify({'error': 'No puedes verificar tu propio arqueo. Se requiere un supervisor diferente.'}), 400

        # Si requiere justificación, las notas son obligatorias
        if arqueo.RequiereJustificacion and not notas_discrepancia.strip():
            return jsonify({'error': 'Este arqueo tiene discrepancias significativas. Las notas de justificación son obligatorias.'}), 400

        # Actualizar el arqueo
        execute_sp(
            cursor,
            'ventas.sp_MarcarArqueoVerificado',
            (current_user.id, notas_discrepancia if notas_discrepancia.strip() else None, arqueo_id),
            fallback_sql="""
            UPDATE ArqueoCaja SET
                VerificadoPorID = ?,
                FechaVerificacion = GETDATE(),
                EstadoArqueo = 'Verificado',
                NotasDiscrepancia = ?
            WHERE ID = ?
        """,
        )

        # Cerrar el turno
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTurnoIDArqueoBloqueo',
            (arqueo_id,),
            fallback_sql="SELECT TurnoID FROM ArqueoCaja WITH(UPDLOCK,HOLDLOCK) WHERE ID = ?",
        )
        turno_id = cursor.fetchone().TurnoID

        execute_sp(
            cursor,
            'ventas.sp_ObtenerMontosSistemaArqueo',
            (arqueo_id,),
            fallback_sql="""
            SELECT EfectivoSistema, TransferenciasSistema FROM ArqueoCaja WHERE ID = ?
        """,
        )
        ar = cursor.fetchone()

        execute_sp(
            cursor,
            'ventas.sp_ObtenerTotalVentasEmitidasTurno',
            (turno_id,),
            fallback_sql="SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE EstadoFiscal='Emitida' AND TurnoID = ?",
        )
        total_ventas = float(cursor.fetchone()[0])

        execute_sp(
            cursor,
            'ventas.sp_CerrarTurnoCajaEnArqueo',
            (float(ar.EfectivoSistema), float(ar.TransferenciasSistema), total_ventas, turno_id),
            fallback_sql="""
            UPDATE TurnosCaja SET Cerrado = 1, FechaCierre = GETDATE(),
                EfectivoCalculado = ?, TransferenciasCalculadas = ?, TotalVentaNeta = ?
            WHERE ID = ?
        """,
        )

        # Marcar como cerrado
        execute_sp(
            cursor,
            'ventas.sp_MarcarArqueoCerrado',
            (arqueo_id,),
            fallback_sql="UPDATE ArqueoCaja SET EstadoArqueo = 'Cerrado' WHERE ID = ?",
        )

        # Audit log
        execute_sp(
            cursor,
            'ventas.sp_InsertarArqueoAuditLog',
            (
                arqueo_id, current_user.id, 'VERIFICADO_Y_CERRADO',
                f'Verificado por {current_user.nombre_completo}. Turno {turno_id} cerrado.',
                request.remote_addr
            ),
            fallback_sql="""
            INSERT INTO ArqueoAuditLog (ArqueoID, UsuarioID, Accion, Detalle, DireccionIP)
            VALUES (?, ?, 'VERIFICADO_Y_CERRADO', ?, ?)
        """,
            fallback_params=(
                arqueo_id, current_user.id,
                f'Verificado por {current_user.nombre_completo}. Turno {turno_id} cerrado.',
                request.remote_addr
            ),
        )

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Arqueo verificado y turno cerrado exitosamente.'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/arqueo/<int:arqueo_id>/detalle', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def arqueo_detalle(arqueo_id):
    """Obtiene el detalle completo de un arqueo, incluyendo denominaciones y audit log."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Denominaciones
    execute_sp(
        cursor,
        'ventas.sp_ObtenerDenominacionesArqueo',
        (arqueo_id,),
        fallback_sql="""
        SELECT TipoMoneda, Denominacion, Cantidad, Subtotal
        FROM ArqueoDetalleDenominacion WHERE ArqueoID = ?
        ORDER BY TipoMoneda, Denominacion DESC
    """,
    )
    denominaciones = [{'tipo': r.TipoMoneda, 'denominacion': float(r.Denominacion),
                       'cantidad': r.Cantidad, 'subtotal': float(r.Subtotal)} for r in cursor.fetchall()]

    # Audit log
    execute_sp(
        cursor,
        'ventas.sp_ObtenerAuditLogArqueo',
        (arqueo_id,),
        fallback_sql="""
        SELECT al.Accion, al.Detalle, u.NombreCompleto, al.FechaAccion
        FROM ArqueoAuditLog al
        JOIN Usuarios u ON al.UsuarioID = u.ID
        WHERE al.ArqueoID = ?
        ORDER BY al.FechaAccion
    """,
    )
    audit_log = [{'accion': r.Accion, 'detalle': r.Detalle, 'usuario': r.NombreCompleto,
                  'fecha': r.FechaAccion.strftime('%d/%m/%Y %H:%M:%S')} for r in cursor.fetchall()]

    conn.close()
    return jsonify({'denominaciones': denominaciones, 'audit_log': audit_log})


# ── Legacy: Cierre rápido (Backward Compatibility) ──


@admin_bp.route('/api/turno/cerrar', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def cerrar_turno():
    return arqueo_etapa1_conteo()


@admin_bp.route('/api/tipo_cambio', methods=['GET'])
@login_required
def obtener_tipo_cambio():
    """Obtiene el tipo de cambio configurado."""
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerConfiguracionClave',
        ('tipo_cambio_usd',),
        fallback_sql="SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'tipo_cambio_usd'",
        fallback_params=(),
    )
    row = cursor.fetchone()
    conn.close()
    tc = float(row.Valor) if row else 36.6243
    return jsonify({'tipo_cambio': tc})


# ============================================================
# MÓDULO DE MERMAS Y PAN FRÍO
# ============================================================


@admin_bp.route('/api/mermas', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def registrar_merma():
    """Registra una merma de producto."""
    datos = request.json
    producto_id = positive_int(datos.get('producto_id'), 'Producto')
    cantidad = positive_int(datos.get('cantidad'), 'Cantidad')
    motivo = datos.get('motivo')
    observaciones = datos.get('observaciones', '')

    if motivo not in ('Pan Frio', 'Defectuoso', 'Merma Horneado', 'Vencido', 'Otro'):
        return jsonify(error='Seleccione un motivo de merma válido.'), 400
    if not all([producto_id, cantidad, motivo]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_RegistrarMerma',
            (int(producto_id), int(cantidad), motivo, observaciones, current_user.id),
            fallback_sql="INSERT INTO Mermas (ProductoID, Cantidad, Motivo, Observaciones, UsuarioID) VALUES (?, ?, ?, ?, ?)",
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Merma registrada'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/mermas', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def obtener_mermas():
    """Obtiene el historial de mermas."""
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_sp(
        cursor,
        'produccion.sp_ListarMermasAdmin',
        fallback_sql="""
        SELECT TOP 100 m.ID, p.Nombre AS Producto, m.Cantidad, m.Motivo, 
               m.Observaciones, u.NombreCompleto AS RegistradoPor, m.Fecha
        FROM Mermas m
        JOIN Productos p ON m.ProductoID = p.ID
        JOIN Usuarios u ON m.UsuarioID = u.ID
        ORDER BY m.Fecha DESC
    """,
    )
    mermas = [{
        'id': r.ID, 'producto': r.Producto, 'cantidad': r.Cantidad,
        'motivo': r.Motivo, 'observaciones': r.Observaciones or '',
        'registrado_por': r.RegistradoPor,
        'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')
    } for r in cursor.fetchall()]
    conn.close()
    return jsonify(mermas)
