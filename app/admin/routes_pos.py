# app/admin/routes_pos.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

@admin_bp.route('/arqueos')
@login_required
@roles_required('Admin', 'SuperAdmin')
def arqueos():
    """Módulo de Arqueos de Caja — Vista principal con historial."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Arqueos recientes con detalles
    cursor.execute("""
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
    """)
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
    cursor.execute("""
        SELECT t.ID, u.NombreCompleto, t.FechaApertura
        FROM TurnosCaja t
        JOIN Usuarios u ON t.UsuarioID = u.ID
        WHERE t.Cerrado = 0
    """)
    turnos_abiertos = [{'id': r.ID, 'usuario': r.NombreCompleto, 'apertura': r.FechaApertura.strftime('%H:%M:%S')} for r in cursor.fetchall()]

    # Umbral de discrepancia
    cursor.execute("SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'umbral_discrepancia_cordobas'")
    row = cursor.fetchone()
    umbral = float(row.Valor) if row else 50.0

    # Estadísticas resumen
    cursor.execute("""
        SELECT
            COUNT(*) AS Total,
            SUM(CASE WHEN ABS(DiferenciaEfectivo) + ABS(DiferenciaTransferencias) < 1 THEN 1 ELSE 0 END) AS Cuadrados,
            SUM(CASE WHEN DiferenciaEfectivo > 0 THEN 1 ELSE 0 END) AS Sobrantes,
            SUM(CASE WHEN DiferenciaEfectivo < 0 THEN 1 ELSE 0 END) AS Faltantes,
            ISNULL(AVG(ABS(DiferenciaEfectivo)), 0) AS PromDiferencia
        FROM ArqueoCaja
        WHERE FechaArqueo >= DATEADD(DAY, -30, GETDATE())
    """)
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
@csrf.exempt
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def arqueo_etapa1_conteo():
    """Etapa 1: Cajero envía conteo desglosado por denominación."""
    datos = request.json
    efectivo_contado = float(datos.get('efectivo_contado', 0))
    transferencias_contadas = float(datos.get('transferencias_contadas', 0))
    dolares_contados = float(datos.get('dolares_contados', 0))
    tipo_cambio = float(datos.get('tipo_cambio', 0))
    observaciones = datos.get('observaciones', '')
    denominaciones = datos.get('denominaciones', [])

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Buscar turno activo del usuario
        cursor.execute("SELECT ID FROM TurnosCaja WHERE UsuarioID = ? AND Cerrado = 0", current_user.id)
        turno_row = cursor.fetchone()
        if not turno_row:
            return jsonify({'error': 'No tienes un turno activo para cerrar'}), 400

        turno_id = turno_row.ID

        # Calcular valores del sistema
        cursor.execute("""
            SELECT
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo' THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
            FROM Pagos p
            JOIN Facturas f ON p.FacturaID = f.ID
            WHERE f.TurnoID = ?
        """, turno_id)
        row = cursor.fetchone()

        efectivo_cordobas = float(row.EfectivoCordobasSistema)
        efectivo_usd_sistema = float(row.EfectivoUSDSistema)
        transferencias_sistema = float(row.TransferenciasSistema)

        # Convertir USD del sistema a córdobas
        efectivo_sistema = efectivo_cordobas + (efectivo_usd_sistema * tipo_cambio if tipo_cambio > 0 else 0)

        # Total contado incluyendo dólares convertidos
        dolares_en_cordobas = dolares_contados * tipo_cambio if tipo_cambio > 0 else 0
        efectivo_total_contado = efectivo_contado + dolares_en_cordobas

        # Diferencias
        dif_efectivo = efectivo_total_contado - efectivo_sistema
        dif_transferencias = transferencias_contadas - transferencias_sistema

        # Determinar si requiere justificación
        cursor.execute("SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'umbral_discrepancia_cordobas'")
        umbral_row = cursor.fetchone()
        umbral = float(umbral_row.Valor) if umbral_row else 50.0
        requiere_justificacion = abs(dif_efectivo) >= umbral or abs(dif_transferencias) >= umbral

        # Total ventas del turno
        cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE TurnoID = ?", turno_id)
        total_ventas = float(cursor.fetchone()[0])

        # Insertar arqueo en estado Pendiente
        cursor.execute("""
            INSERT INTO ArqueoCaja (TurnoID, UsuarioID, EfectivoContado, TransferenciasContadas,
                DolaresContados, TipoCambioUsado, EfectivoSistema, TransferenciasSistema,
                DiferenciaEfectivo, DiferenciaTransferencias, Observaciones,
                EstadoArqueo, RequiereJustificacion)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
        """, turno_id, current_user.id, efectivo_contado, transferencias_contadas,
            dolares_contados, tipo_cambio if tipo_cambio > 0 else None,
            efectivo_sistema, transferencias_sistema,
            dif_efectivo, dif_transferencias, observaciones,
            1 if requiere_justificacion else 0)

        arqueo_id = cursor.fetchone()[0]

        # Insertar detalle por denominación
        for d in denominaciones:
            if int(d.get('cantidad', 0)) > 0:
                cursor.execute("""
                    INSERT INTO ArqueoDetalleDenominacion (ArqueoID, TipoMoneda, Denominacion, Cantidad)
                    VALUES (?, ?, ?, ?)
                """, arqueo_id, d.get('tipo', 'NIO'), float(d.get('denominacion', 0)), int(d.get('cantidad', 0)))

        # Audit log
        cursor.execute("""
            INSERT INTO ArqueoAuditLog (ArqueoID, UsuarioID, Accion, Detalle, DireccionIP)
            VALUES (?, ?, 'CONTEO_REGISTRADO', ?, ?)
        """, arqueo_id, current_user.id,
            f'Efectivo contado: C${efectivo_total_contado:.2f} | Sistema: C${efectivo_sistema:.2f} | Dif: C${dif_efectivo:.2f}',
            request.remote_addr)

        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Conteo registrado. Pendiente de verificación de gerencia.',
            'arqueo_id': arqueo_id,
            'arqueo': {
                'efectivo_sistema': efectivo_sistema,
                'transferencias_sistema': transferencias_sistema,
                'efectivo_contado': efectivo_total_contado,
                'transferencias_contadas': transferencias_contadas,
                'diferencia_efectivo': dif_efectivo,
                'diferencia_transferencias': dif_transferencias,
                'total_ventas': total_ventas,
                'requiere_justificacion': requiere_justificacion
            }
        })
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/arqueo/<int:arqueo_id>/verificar', methods=['POST'])
@csrf.exempt
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
        cursor.execute("SELECT UsuarioID, RequiereJustificacion, EstadoArqueo FROM ArqueoCaja WHERE ID = ?", arqueo_id)
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
        cursor.execute("""
            UPDATE ArqueoCaja SET
                VerificadoPorID = ?,
                FechaVerificacion = GETDATE(),
                EstadoArqueo = 'Verificado',
                NotasDiscrepancia = ?
            WHERE ID = ?
        """, current_user.id, notas_discrepancia if notas_discrepancia.strip() else None, arqueo_id)

        # Cerrar el turno
        cursor.execute("SELECT TurnoID FROM ArqueoCaja WHERE ID = ?", arqueo_id)
        turno_id = cursor.fetchone().TurnoID

        cursor.execute("""
            SELECT EfectivoSistema, TransferenciasSistema FROM ArqueoCaja WHERE ID = ?
        """, arqueo_id)
        ar = cursor.fetchone()

        cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE TurnoID = ?", turno_id)
        total_ventas = float(cursor.fetchone()[0])

        cursor.execute("""
            UPDATE TurnosCaja SET Cerrado = 1, FechaCierre = GETDATE(),
                EfectivoCalculado = ?, TransferenciasCalculadas = ?, TotalVentaNeta = ?
            WHERE ID = ?
        """, float(ar.EfectivoSistema), float(ar.TransferenciasSistema), total_ventas, turno_id)

        # Marcar como cerrado
        cursor.execute("UPDATE ArqueoCaja SET EstadoArqueo = 'Cerrado' WHERE ID = ?", arqueo_id)

        # Audit log
        cursor.execute("""
            INSERT INTO ArqueoAuditLog (ArqueoID, UsuarioID, Accion, Detalle, DireccionIP)
            VALUES (?, ?, 'VERIFICADO_Y_CERRADO', ?, ?)
        """, arqueo_id, current_user.id,
            f'Verificado por {current_user.nombre_completo}. Turno {turno_id} cerrado.',
            request.remote_addr)

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
    cursor.execute("""
        SELECT TipoMoneda, Denominacion, Cantidad, Subtotal
        FROM ArqueoDetalleDenominacion WHERE ArqueoID = ?
        ORDER BY TipoMoneda, Denominacion DESC
    """, arqueo_id)
    denominaciones = [{'tipo': r.TipoMoneda, 'denominacion': float(r.Denominacion),
                       'cantidad': r.Cantidad, 'subtotal': float(r.Subtotal)} for r in cursor.fetchall()]

    # Audit log
    cursor.execute("""
        SELECT al.Accion, al.Detalle, u.NombreCompleto, al.FechaAccion
        FROM ArqueoAuditLog al
        JOIN Usuarios u ON al.UsuarioID = u.ID
        WHERE al.ArqueoID = ?
        ORDER BY al.FechaAccion
    """, arqueo_id)
    audit_log = [{'accion': r.Accion, 'detalle': r.Detalle, 'usuario': r.NombreCompleto,
                  'fecha': r.FechaAccion.strftime('%d/%m/%Y %H:%M:%S')} for r in cursor.fetchall()]

    conn.close()
    return jsonify({'denominaciones': denominaciones, 'audit_log': audit_log})


# ── Legacy: Cierre rápido (Backward Compatibility) ──


@admin_bp.route('/api/turno/cerrar', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def cerrar_turno():
    """Cierre de turno con arqueo ciego de caja."""
    datos = request.json
    efectivo_contado = float(datos.get('efectivo_contado', 0))
    transferencias_contadas = float(datos.get('transferencias_contadas', 0))
    dolares_contados = float(datos.get('dolares_contados', 0))
    tipo_cambio = float(datos.get('tipo_cambio', 0))
    observaciones = datos.get('observaciones', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Buscar turno activo del usuario
        cursor.execute("SELECT ID FROM TurnosCaja WHERE UsuarioID = ? AND Cerrado = 0", current_user.id)
        turno_row = cursor.fetchone()
        if not turno_row:
            return jsonify({'error': 'No tienes un turno activo para cerrar'}), 400

        turno_id = turno_row.ID

        # Calcular valores del sistema
        # Se suma el Efectivo en córdobas y el Efectivo USD convertido a córdobas según el tipo_cambio ingresado para el arqueo.
        cursor.execute("""
            SELECT 
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo' THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
            FROM Pagos p
            JOIN Facturas f ON p.FacturaID = f.ID
            WHERE f.TurnoID = ?
        """, turno_id)
        row = cursor.fetchone()
        
        efectivo_cordobas = float(row.EfectivoCordobasSistema)
        efectivo_usd_sistema = float(row.EfectivoUSDSistema)
        transferencias_sistema = float(row.TransferenciasSistema)

        # Convertir los dólares registrados en sistema a córdobas
        efectivo_sistema = efectivo_cordobas + (efectivo_usd_sistema * tipo_cambio if tipo_cambio > 0 else 0)

        # Convertir dólares a córdobas
        dolares_en_cordobas = dolares_contados * tipo_cambio if tipo_cambio > 0 else 0
        efectivo_total_contado = efectivo_contado + dolares_en_cordobas

        # Calcular diferencias
        dif_efectivo = efectivo_total_contado - efectivo_sistema
        dif_transferencias = transferencias_contadas - transferencias_sistema

        # Total venta neta del turno
        cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE TurnoID = ?", turno_id)
        total_ventas = float(cursor.fetchone()[0])

        # Insertar arqueo
        cursor.execute("""
            INSERT INTO ArqueoCaja (TurnoID, UsuarioID, EfectivoContado, TransferenciasContadas, 
                DolaresContados, TipoCambioUsado, EfectivoSistema, TransferenciasSistema,
                DiferenciaEfectivo, DiferenciaTransferencias, Observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, turno_id, current_user.id, efectivo_contado, transferencias_contadas,
            dolares_contados, tipo_cambio if tipo_cambio > 0 else None,
            efectivo_sistema, transferencias_sistema,
            dif_efectivo, dif_transferencias, observaciones)

        # Cerrar turno
        cursor.execute("""
            UPDATE TurnosCaja SET Cerrado = 1, FechaCierre = GETDATE(), 
                EfectivoCalculado = ?, TransferenciasCalculadas = ?, TotalVentaNeta = ?
            WHERE ID = ?
        """, efectivo_sistema, transferencias_sistema, total_ventas, turno_id)

        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Turno cerrado y arqueo registrado',
            'arqueo': {
                'efectivo_sistema': efectivo_sistema,
                'transferencias_sistema': transferencias_sistema,
                'efectivo_contado': efectivo_total_contado,
                'transferencias_contadas': transferencias_contadas,
                'diferencia_efectivo': dif_efectivo,
                'diferencia_transferencias': dif_transferencias,
                'total_ventas': total_ventas
            }
        })
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/tipo_cambio', methods=['GET'])
@login_required
def obtener_tipo_cambio():
    """Obtiene el tipo de cambio configurado."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'tipo_cambio_usd'")
    row = cursor.fetchone()
    conn.close()
    tc = float(row.Valor) if row else 36.6243
    return jsonify({'tipo_cambio': tc})


# ============================================================
# MÓDULO DE MERMAS Y PAN FRÍO
# ============================================================


@admin_bp.route('/api/mermas', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def registrar_merma():
    """Registra una merma de producto."""
    datos = request.json
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad')
    motivo = datos.get('motivo')
    observaciones = datos.get('observaciones', '')

    if not all([producto_id, cantidad, motivo]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Mermas (ProductoID, Cantidad, Motivo, Observaciones, UsuarioID) VALUES (?, ?, ?, ?, ?)",
            int(producto_id), int(cantidad), motivo, observaciones, current_user.id
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
    cursor.execute("""
        SELECT TOP 100 m.ID, p.Nombre AS Producto, m.Cantidad, m.Motivo, 
               m.Observaciones, u.NombreCompleto AS RegistradoPor, m.Fecha
        FROM Mermas m
        JOIN Productos p ON m.ProductoID = p.ID
        JOIN Usuarios u ON m.UsuarioID = u.ID
        ORDER BY m.Fecha DESC
    """)
    mermas = [{
        'id': r.ID, 'producto': r.Producto, 'cantidad': r.Cantidad,
        'motivo': r.Motivo, 'observaciones': r.Observaciones or '',
        'registrado_por': r.RegistradoPor,
        'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')
    } for r in cursor.fetchall()]
    conn.close()
    return jsonify(mermas)


# ============================================================
# MÓDULO DE ESTADÍSTICA Y REPORTES
# ============================================================


