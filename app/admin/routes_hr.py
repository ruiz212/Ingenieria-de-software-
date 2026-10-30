# app/admin/routes_hr.py
from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
import json
import traceback
import base64
import os
import uuid

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime, date, timedelta
from decimal import Decimal
from app.services.validation import amount, positive_int, required_text, validate_cedula_nicaragua, validate_telefono_nicaragua
from app.services.hr_calculations import (
    as_date, absent_dates, liquidation, can_mark_exit,
    resolver_horario_y_clasificar_asistencia,
)
from app.services.payroll_engine import (
    calcular_planilla_completa,
    calcular_saldo_vacaciones_empleado,
    generar_plan_recomendado_vacaciones,
    calcular_tasa_provision_indemnizacion,
)
from app.services.business_time import business_now


class _NominaConflictError(ValueError):
    """Conflicto de estado / idempotencia en operaciones de nómina (HTTP 409)."""
    pass


def _fecha_contable_periodo(periodo_fin):
    """Retorna la fecha contable dentro del mes del período sin quedar en el futuro si es el mes en curso."""
    fin = date.fromisoformat(str(periodo_fin))
    ahora = business_now()
    if (fin.year, fin.month) == (ahora.year, ahora.month) and ahora.date() < fin:
        return ahora
    return datetime(fin.year, fin.month, fin.day, 17, 0, 0)


def _validar_no_periodo_futuro(inicio, fin, aguinaldo=False):
    inicio_dt = as_date(inicio)
    fin_dt = as_date(fin)
    hoy = business_now().date()
    if not aguinaldo:
        if (inicio_dt.year, inicio_dt.month) > (hoy.year, hoy.month) or (fin_dt.year, fin_dt.month) > (hoy.year, hoy.month):
            raise ValueError('No se puede generar ni contabilizar nómina para períodos futuros.')
    else:
        if fin_dt.year > hoy.year:
            raise ValueError('No se puede generar ni contabilizar aguinaldo para años futuros.')


def validar_periodo_nomina(cursor, empleado_id, inicio, fin, aguinaldo=False):
    inicio = date.fromisoformat(str(inicio)); fin = date.fromisoformat(str(fin))
    if not aguinaldo:
        import calendar
        if inicio.day != 1 or fin != date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1]):
            raise ValueError('El cálculo mensual requiere el primer y último día del mismo mes.')
    if fin < inicio:
        raise ValueError('El período final no puede ser anterior al inicial.')
    _validar_no_periodo_futuro(inicio, fin, aguinaldo=aguinaldo)
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerEmpleadoBloqueo',
        (empleado_id,),
        fallback_sql='SELECT ID FROM Empleados WITH(UPDLOCK,HOLDLOCK) WHERE ID=?',
    )
    if not cursor.fetchone():
        raise ValueError('Empleado inexistente.')
    # Aguinaldo se guarda actualmente como nómina sin salario base.
    comparison = '=' if aguinaldo else '>'
    sp_name = 'rrhh.sp_VerificarNominaExistenteAguinaldo' if aguinaldo else 'rrhh.sp_VerificarNominaExistenteMensual'
    execute_sp(
        cursor,
        sp_name,
        (empleado_id, fin, inicio),
        fallback_sql=f"SELECT ID, Estado FROM Nomina WHERE EmpleadoID=? AND PeriodoInicio<=? AND PeriodoFin>=? AND SalarioBruto {comparison} 0 AND Estado IN ('Contabilizada', 'Pagada')",
    )
    if cursor.fetchone():
        raise ValueError('Ya existe una nómina para este empleado y período. Revise el registro anterior.')
    # Si quedaron borradores previos sin asiento contable, se limpian antes de generar la nómina contabilizada.
    execute_sp(
        cursor,
        'rrhh.sp_LimpiarBorradoresNominaPeriodo',
        (empleado_id, fin, inicio, 1 if aguinaldo else 0),
        fallback_sql=f"DELETE FROM Nomina WHERE EmpleadoID=? AND PeriodoInicio<=? AND PeriodoFin>=? AND SalarioBruto {comparison} 0 AND Estado = 'Borrador'",
    )


def _calcular_y_aplicar_vales_periodo(cursor, usuario_id, fecha_fin_periodo, neto_disponible):
    """Filtra vales pendientes por Fecha <= fecha_fin_periodo y aplica hasta neto_disponible (orden cronológico)."""
    neto_disp = max(Decimal('0.00'), amount(neto_disponible))
    if not usuario_id or neto_disp <= Decimal('0.00'):
        return Decimal('0.00')

    fecha_fin_iso = as_date(fecha_fin_periodo).isoformat()
    execute_sp(
        cursor,
        'contabilidad.sp_ListarValesPendientesUsuarioHastaFecha',
        (int(usuario_id), fecha_fin_iso),
        fallback_sql=(
            "SELECT ID, Monto, Fecha FROM ValesEmpleados "
            "WHERE EmpleadoID = ? AND Descontado = 0 AND CAST(Fecha AS DATE) <= ? "
            "ORDER BY Fecha ASC, ID ASC"
        ),
    )
    rows = cursor.fetchall() or []
    restante = neto_disp
    total_descontado = Decimal('0.00')
    completos_ids = []
    parcial = None

    for row in rows:
        if restante <= Decimal('0.00'):
            break
        vid = getattr(row, 'ID', None)
        monto_raw = getattr(row, 'Monto', None)
        if vid is None and isinstance(row, (tuple, list)):
            vid = row[0]
            monto_raw = row[1] if len(row) > 1 else row[0]
        monto_vale = amount(monto_raw or 0)
        if monto_vale <= Decimal('0.00'):
            continue
        if monto_vale <= restante:
            total_descontado += monto_vale
            restante -= monto_vale
            if vid is not None:
                completos_ids.append(int(vid))
        else:
            aplicado = restante
            nuevo_saldo = amount(monto_vale - aplicado)
            total_descontado += aplicado
            restante = Decimal('0.00')
            if vid is not None:
                parcial = (int(vid), nuevo_saldo)
            break

    for vid in completos_ids:
        execute_sp(
            cursor,
            'contabilidad.sp_MarcarValeDescontadoPorID',
            (vid,),
            fallback_sql="UPDATE ValesEmpleados SET Descontado = 1 WHERE ID = ? AND Descontado = 0",
        )
    if parcial is not None:
        vid, nuevo_saldo = parcial
        execute_sp(
            cursor,
            'contabilidad.sp_ActualizarSaldoValeParcialPorID',
            (nuevo_saldo, vid),
            fallback_sql="UPDATE ValesEmpleados SET Monto = ?, Descontado = 0 WHERE ID = ? AND Descontado = 0",
        )

    return amount(total_descontado)


def _contabilizar_nomina_segura(cursor, usuario_id, nomina_id, empleado_nombre, salario_bruto,
                                inss_laboral, ir_retenido, inss_patronal, inatec,
                                pension_alimenticia=0, vales_descontados=0, salario_neto=0,
                                cargo='Admin', ip=None, fecha=None,
                                provision_vacaciones=0, provision_aguinaldo=0, provision_indemnizacion=0,
                                deduccion_prestamos=0, cobro_perdidas=0, viaticos=0, depreciacion_vehiculo=0):
    """Contabiliza la nómina integrando ingresos salariales/no salariales, deducciones y provisiones patronales."""
    from app.services.contabilidad_service import ContabilidadService
    return ContabilidadService.contabilizar_nomina(
        cursor=cursor,
        usuario_id=usuario_id,
        nomina_id=nomina_id,
        empleado_nombre=empleado_nombre,
        salario_bruto=salario_bruto,
        inss_laboral=inss_laboral,
        ir_retenido=ir_retenido,
        inss_patronal=inss_patronal,
        inatec=inatec,
        pension_alimenticia=pension_alimenticia,
        vales_descontados=vales_descontados,
        salario_neto=salario_neto,
        cargo=cargo,
        ip=ip,
        fecha=fecha,
        provision_vacaciones=provision_vacaciones,
        provision_aguinaldo=provision_aguinaldo,
        provision_indemnizacion=provision_indemnizacion,
        deduccion_prestamos=deduccion_prestamos,
        cobro_perdidas=cobro_perdidas,
        viaticos=viaticos,
        depreciacion_vehiculo=depreciacion_vehiculo,
    )


def calcular_deducciones_judiciales(cursor, empleado_id, salario_neto_pre, fecha):
    """Calcula obligaciones vigentes por porcentaje y monto fijo."""
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerDeduccionesJudicialesVigentes',
        (empleado_id, fecha, fecha),
        fallback_sql=(
            "SELECT PorcentajeSalarioNeto, MontoFijo FROM DeduccionesJudiciales "
            "WHERE EmpleadoID=? AND Activa=1 AND FechaInicio<=? "
            "AND (FechaFin IS NULL OR FechaFin>=?)"
        ),
    )
    rows = cursor.fetchall()
    porcentaje = min(sum(float(row.PorcentajeSalarioNeto or 0) for row in rows), 60)
    monto_fijo = sum(float(row.MontoFijo or 0) for row in rows)
    return min(max(0, salario_neto_pre * porcentaje / 100 + monto_fijo), max(0, salario_neto_pre))


@admin_bp.route('/rrhh')
@login_required
@roles_required('Admin', 'SuperAdmin')
def rrhh():
    """Módulo de Recursos Humanos con cumplimiento de ley nicaragüense."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        execute_sp(
            cursor, 'rrhh.sp_ListarPerfilesPuesto',
            fallback_sql='SELECT Cargo,PerfilPuesto,Obligaciones,RequisitosCompetencias,ActualizadoEn,Activo FROM rrhh.PerfilesPuesto ORDER BY Cargo',
        )
        perfiles = [{
            'cargo': row.Cargo, 'perfil': row.PerfilPuesto,
            'obligaciones': row.Obligaciones, 'competencias': row.RequisitosCompetencias,
            'activo': bool(getattr(row, 'Activo', 1)) if (hasattr(row, 'Activo') and getattr(row, 'Activo') is not None) else True,
        } for row in cursor.fetchall()]
    except Exception:
        perfiles = []
    perfil_por_cargo = {row['cargo'].casefold(): row for row in perfiles}

    # Empleados activos
    execute_sp(
        cursor,
        'rrhh.sp_ListarEmpleadosConUsuario',
        fallback_sql="""
        SELECT e.*, u.Username 
        FROM Empleados e 
        LEFT JOIN Usuarios u ON e.UsuarioID = u.ID
        ORDER BY e.NombreCompleto
    """,
    )
    empleados = []
    for r in cursor.fetchall():
        empleados.append({
            'id': r.ID, 'nombre': r.NombreCompleto, 'cedula': r.Cedula,
            'cargo': r.Cargo, 'fecha_ingreso': r.FechaIngreso.strftime('%d/%m/%Y') if r.FechaIngreso else '',
            'salario_base': float(r.SalarioBase), 'tipo_jornada': r.TipoJornada,
            'tipo_contrato': r.TipoContrato, 'forma_pago': r.FormaPago,
            'estado': r.EstadoEmpleado, 'telefono': r.Telefono or '',
            'numero_inss': r.NumeroINSS or '', 'username': r.Username or '',
            'consentimiento': bool(r.ConsentimientoDatos),
            'hora_entrada': r.HoraEntrada.strftime('%H:%M') if r.HoraEntrada else '',
            'hora_salida': r.HoraSalida.strftime('%H:%M') if r.HoraSalida else '',
            'perfil_puesto': perfil_por_cargo.get(r.Cargo.casefold()),
        })

    # Nóminas recientes
    execute_sp(
        cursor,
        'rrhh.sp_ListarNominasRecientes',
        fallback_sql="""
        SELECT TOP 50 n.ID, e.NombreCompleto, e.Cargo, n.PeriodoInicio, n.PeriodoFin,
               n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto,
               n.INSSPatronal, n.INATEC, n.Estado,
               n.SalarioBruto, n.OtrosIngresos,
               a.ID AS AsientoID, a.NumeroComprobante
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        OUTER APPLY (
            SELECT TOP 1 ID, NumeroComprobante
            FROM AsientosDiario
            WHERE ReferenciaExterna = CONCAT('NOM-', n.ID)
              AND Estado = 'Contabilizado'
            ORDER BY ID DESC
        ) a
        ORDER BY CASE WHEN n.SalarioBruto > 0 THEN 0 ELSE 1 END,
                 n.PeriodoFin DESC,
                 n.ID DESC
    """,
    )
    nominas = [{
        'id': r.ID,
        'empleado': r.NombreCompleto,
        'cargo': getattr(r, 'Cargo', '') or '',
        'periodo': f"{r.PeriodoInicio.strftime('%d/%m/%Y')} - {r.PeriodoFin.strftime('%d/%m/%Y')}",
        'mes_anio': r.PeriodoFin.strftime('%Y-%m') if r.PeriodoFin else '',
        'devengado': float(r.TotalDevengado),
        'deducciones': float(r.TotalDeducciones),
        'neto': float(r.SalarioNeto),
        'inss_patronal': float(getattr(r, 'INSSPatronal', 0) or 0),
        'inatec': float(getattr(r, 'INATEC', 0) or 0),
        'costo_total': float(r.TotalDevengado) + float(getattr(r, 'INSSPatronal', 0) or 0) + float(getattr(r, 'INATEC', 0) or 0),
        'estado': r.Estado,
        'asiento_id': getattr(r, 'AsientoID', None),
        'comprobante': getattr(r, 'NumeroComprobante', None) or (f"NOM-{r.ID}" if r.Estado in ('Contabilizada', 'Pagada') else None),
        'es_aguinaldo': float(r.SalarioBruto) == 0 and float(r.OtrosIngresos) > 0
    } for r in cursor.fetchall()]

    # Configuraciones de tasas
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerTasasLaboralesConfig',
        fallback_sql="SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')",
    )
    tasas = {r.Clave: r.Valor for r in cursor.fetchall()}

    # Conteo de empleados activos (para determinar tasa patronal)
    execute_sp(
        cursor,
        'rrhh.sp_ContarEmpleadosActivos',
        fallback_sql="SELECT COUNT(*) FROM Empleados WHERE EstadoEmpleado = 'Activo'",
    )
    total_activos = cursor.fetchone()[0]

    # Asistencia de hoy (Monitor)
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerAsistenciaPorFechaMonitor',
        (fecha_hoy,),
        fallback_sql="""
        SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, e.NombreCompleto, e.Cargo
        FROM Asistencia a 
        JOIN Empleados e ON a.EmpleadoID = e.ID
        WHERE a.Fecha = ?
        ORDER BY a.HoraEntrada DESC
    """,
    )
    monitor_hoy = [{
        'empleado': r.NombreCompleto,
        'cargo': r.Cargo,
        'entrada': r.HoraEntrada.strftime('%H:%M') if r.HoraEntrada else '-',
        'salida': r.HoraSalida.strftime('%H:%M') if r.HoraSalida else '-',
        'estado': r.EstadoEntrada
    } for r in cursor.fetchall()]

    conn.close()

    return render_template('admin/rrhh.html', user=current_user,
        empleados=empleados, nominas=nominas, tasas=tasas, total_activos=total_activos,
        monitor_hoy=monitor_hoy, datetime=datetime, perfiles=perfiles,
        fecha_hoy=business_now().strftime('%Y-%m-%d'))


@admin_bp.route('/api/rrhh/puestos', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def guardar_perfil_puesto():
    """Mantiene obligaciones contractuales sin intervenir la remuneración."""
    data = request.get_json(silent=True) or {}
    limits = {'cargo': 100, 'perfil_puesto': 1000,
              'obligaciones': 2000, 'requisitos_competencias': 1000}
    fields = {}
    for key, limit in limits.items():
        value = str(data.get(key) or '').strip()
        if not value or len(value) > limit or '\x00' in value:
            return jsonify(error=f'Complete {key} (máximo {limit} caracteres).'), 400
        fields[key] = value
    conn = get_db_connection()
    try:
        execute_sp(
            conn.cursor(), 'rrhh.sp_GuardarPerfilPuesto',
            (fields['cargo'], fields['perfil_puesto'], fields['obligaciones'],
             fields['requisitos_competencias'], current_user.id, request.remote_addr),
        )
        conn.commit()
        return jsonify(status='success', cargo=fields['cargo'])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/puestos/estado', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def cambiar_estado_perfil_puesto():
    """Activa o desactiva un perfil de puesto (Soft Delete)."""
    data = request.get_json(silent=True) or {}
    cargo = str(data.get('cargo') or '').strip()
    if not cargo:
        return jsonify(error='Debe especificar un cargo.'), 400
    activo = 1 if data.get('activo') in (True, 1, '1', 'true', 'True') else 0
    conn = get_db_connection()
    try:
        execute_sp(
            conn.cursor(), 'rrhh.sp_CambiarEstadoPerfilPuesto',
            (cargo, activo, current_user.id, request.remote_addr),
            fallback_sql="UPDATE rrhh.PerfilesPuesto SET Activo=?, ActualizadoEn=SYSUTCDATETIME() WHERE Cargo=?",
        )
        conn.commit()
        return jsonify(status='success', cargo=cargo, activo=bool(activo))
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/asistencia_hoy_json', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def rrhh_asistencia_hoy_json():
    """Endpoint para polling automático del monitor de asistencia."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaPorFechaMonitor',
            (fecha_hoy,),
            fallback_sql="""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, e.NombreCompleto, e.Cargo
            FROM Asistencia a 
            JOIN Empleados e ON a.EmpleadoID = e.ID
            WHERE a.Fecha = ?
            ORDER BY a.HoraEntrada DESC
        """,
        )
        monitor_hoy = [{
            'empleado': r.NombreCompleto,
            'cargo': r.Cargo,
            'entrada': r.HoraEntrada.strftime('%H:%M') if r.HoraEntrada else '-',
            'salida': r.HoraSalida.strftime('%H:%M') if r.HoraSalida else '-',
            'estado': r.EstadoEntrada
        } for r in cursor.fetchall()]
        
        return jsonify({'status': 'success', 'data': monitor_hoy})
    except Exception as e:
        import logging
        logging.error(f"Error en polling de asistencia: {e}")
        return jsonify({'error': 'Error interno'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/escala-salarial', methods=['GET'])
@admin_bp.route('/api/rrhh/escala-salarial/<path:cargo>', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def obtener_salario_escala(cargo=None):
    """Consulta la escala salarial por cargo para autocompletar el salario base."""
    target_cargo = cargo or request.args.get('cargo', '')
    target_cargo = str(target_cargo).strip()
    if not target_cargo:
        return jsonify({'status': 'error', 'message': 'Debe especificar un cargo.'}), 400

    from app.models import EscalaSalarial
    escala = EscalaSalarial.get_by_cargo(target_cargo)
    if not escala:
        return jsonify({'status': 'error', 'message': f'Cargo "{target_cargo}" no encontrado en la escala salarial.'}), 404

    return jsonify({
        'status': 'success',
        'id': escala.id,
        'nivel': escala.nivel,
        'cargo': escala.cargo,
        'limite_inferior': escala.limite_inferior,
        'limite_superior': escala.limite_superior,
        'salario_base': escala.salario_base,
    })


@admin_bp.route('/api/rrhh/empleado', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_empleado():
    """Crea un nuevo empleado en el expediente."""
    datos = request.get_json(silent=True) or {}
    datos['fecha_ingreso'] = datos.get('fecha_ingreso') or business_now().strftime('%Y-%m-%d')
    campos_requeridos = ['nombre', 'cedula', 'cargo', 'fecha_ingreso', 'salario_base']
    if not all(datos.get(c) for c in campos_requeridos):
        return jsonify({'error': 'Faltan campos requeridos'}), 400
    try:
        date.fromisoformat(str(datos['fecha_ingreso']))
    except ValueError:
        return jsonify(error='Fecha de ingreso inválida.'), 400
    try:
        cedula_validada = validate_cedula_nicaragua(datos.get('cedula'), field_name='Cédula', optional=False)
        telefono_validado = validate_telefono_nicaragua(datos.get('telefono'), field_name='Teléfono', optional=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor, 'rrhh.sp_ObtenerPerfilPuestoPorCargo',
            (str(datos['cargo']).strip(),),
            fallback_sql='SELECT Cargo FROM rrhh.PerfilesPuesto WHERE Cargo=?',
        )
        if not cursor.fetchone():
            return jsonify(error='Seleccione un perfil de puesto registrado.'), 400
        foto_path = None
        descriptor_str = None
        if 'foto' in datos and datos['foto']:
            from app.services.face_service import face_service
            resultado_ia = face_service.procesar_imagen_registro_base64(datos['foto'])
            if resultado_ia['status'] == 'success':
                descriptor_str = json.dumps(resultado_ia['descriptor'])
            else:
                import logging
                logging.warning(f"No se pudo extraer descriptor SFace: {resultado_ia['message']}")

            try:
                header, encoded = datos['foto'].split(",", 1)
                ext = "png" if "png" in header else "jpg"
                filename = f"face_{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(current_app.static_folder, 'uploads', 'faces', filename)
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(encoded))
                foto_path = f"/static/uploads/faces/{filename}"
            except Exception as e:
                import logging
                logging.error(f"Error procesando foto: {e}")

        execute_sp(
            cursor,
            'rrhh.sp_CrearEmpleado',
            (
                datos.get('nombre'), cedula_validada,
                datos.get('fecha_nacimiento') or None, datos.get('genero') or None,
                datos.get('direccion') or None, telefono_validado or None,
                datos.get('correo') or None, datos.get('numero_inss') or None,
                datos.get('cargo'), datos.get('fecha_ingreso'),
                datos.get('tipo_contrato', 'Indefinido'),
                datos.get('fecha_fin_contrato') or None,
                datos.get('tipo_jornada', 'Diurna'),
                float(datos.get('salario_base')),
                datos.get('forma_pago', 'Mensual'),
                1 if datos.get('consentimiento') else 0,
                foto_path,
                datos.get('hora_entrada') or None,
                datos.get('hora_salida') or None,
                descriptor_str
            ),
            fallback_sql="""
            INSERT INTO Empleados (NombreCompleto, Cedula, FechaNacimiento, Genero, Direccion,
                Telefono, CorreoElectronico, NumeroINSS, Cargo, FechaIngreso, TipoContrato, FechaFinContrato,
                TipoJornada, SalarioBase, FormaPago, ConsentimientoDatos, FechaConsentimiento, FotoPerfil, HoraEntrada, HoraSalida, FaceDescriptor)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, ?, ?)
        """,
        )
        
        row = cursor.fetchone()
        nuevo_id = row.ID if row else None
        conn.commit()

        if nuevo_id and descriptor_str:
            from app.services.face_service import face_service
            face_service.actualizar_cache_empleado(nuevo_id, json.loads(descriptor_str))
            
        return jsonify({'status': 'success', 'mensaje': 'Empleado registrado'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/empleado/<int:id>', methods=['DELETE'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def eliminar_empleado(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_SuspenderEmpleado',
            (id,),
            fallback_sql="UPDATE Empleados SET EstadoEmpleado='Suspendido' WHERE ID=?",
        )
        if cursor.rowcount == 0:
            return jsonify({'error': 'Empleado no encontrado'}), 404
            
        conn.commit()
        from app.services.face_service import face_service
        if id in face_service.encodings_cache:
            del face_service.encodings_cache[id]
            
        return jsonify({'status': 'success', 'mensaje': 'Empleado suspendido. Se conserva todo el historial laboral y contable.'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error eliminando empleado: {e}")
        if '547' in str(e) or 'REFERENCE' in str(e):
            return jsonify({'error': 'Aún existen otras dependencias fuertes. Bórralo manualmente o ponlo Inactivo.'}), 400
        return jsonify({'error': 'Error interno al eliminar el empleado'}), 500
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/empleado/<int:id>/horario', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def actualizar_horario_empleado(id):
    datos = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hora_entrada = datos.get('hora_entrada') or None
        hora_salida = datos.get('hora_salida') or None
        execute_sp(
            cursor,
            'rrhh.sp_ActualizarHorarioEmpleado',
            (hora_entrada, hora_salida, id),
            fallback_sql="UPDATE Empleados SET HoraEntrada = ?, HoraSalida = ? WHERE ID = ?",
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Horario actualizado'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error updating schedule: {e}")
        return jsonify({'error': 'Error interno'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/deducciones', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def deducciones_judiciales():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'GET':
            execute_sp(
                cursor,
                'rrhh.sp_ListarDeduccionesJudiciales',
                fallback_sql=(
                    "SELECT d.ID, d.EmpleadoID, e.NombreCompleto, d.TipoDeduccion, d.Beneficiario, "
                    "d.PorcentajeSalarioNeto, d.MontoFijo, d.NumeroJuzgado, d.FechaInicio, d.FechaFin, d.Activa "
                    "FROM DeduccionesJudiciales d JOIN Empleados e ON e.ID=d.EmpleadoID ORDER BY d.Activa DESC, d.ID DESC"
                ),
            )
            return jsonify([{
                'id': row.ID, 'empleado_id': row.EmpleadoID, 'empleado': row.NombreCompleto,
                'tipo': row.TipoDeduccion, 'beneficiario': row.Beneficiario,
                'porcentaje': float(row.PorcentajeSalarioNeto),
                'monto_fijo': float(row.MontoFijo) if row.MontoFijo is not None else None,
                'juzgado': row.NumeroJuzgado, 'fecha_inicio': row.FechaInicio.isoformat(),
                'fecha_fin': row.FechaFin.isoformat() if row.FechaFin else None, 'activa': bool(row.Activa)
            } for row in cursor.fetchall()])

        data = request.get_json(silent=True) or {}
        empleado_id = positive_int(data.get('empleado_id'), 'Empleado')
        tipo = data.get('tipo')
        if tipo not in ('Pension Alimenticia', 'Embargo Comercial'):
            raise ValueError('Tipo de deducción inválido.')
        beneficiario = required_text(data.get('beneficiario'), 'Beneficiario', 150)
        porcentaje = amount(data.get('porcentaje', 0), 'Porcentaje', maximum=60)
        monto_fijo = amount(data.get('monto_fijo', 0), 'Monto fijo')
        if porcentaje == 0 and monto_fijo == 0:
            raise ValueError('Indique un porcentaje o un monto fijo.')
        fecha_inicio = data.get('fecha_inicio')
        if not fecha_inicio:
            raise ValueError('La fecha de inicio es obligatoria.')
        datetime.fromisoformat(fecha_inicio)
        execute_sp(
            cursor,
            'rrhh.sp_VerificarEmpleadoExiste',
            (empleado_id,),
            fallback_sql="SELECT ID FROM Empleados WHERE ID=?",
        )
        if not cursor.fetchone():
            return jsonify(error='Empleado inexistente.'), 400
        execute_sp(
            cursor,
            'rrhh.sp_InsertarDeduccionJudicial',
            (
                empleado_id, tipo, beneficiario, porcentaje, monto_fijo or None,
                (data.get('juzgado') or '').strip()[:50] or None, fecha_inicio, data.get('fecha_fin') or None
            ),
            fallback_sql=(
                "INSERT INTO DeduccionesJudiciales (EmpleadoID,TipoDeduccion,Beneficiario,PorcentajeSalarioNeto,MontoFijo,NumeroJuzgado,FechaInicio,FechaFin) "
                "VALUES (?,?,?,?,?,?,?,?)"
            ),
        )
        conn.commit()
        return jsonify(status='success', mensaje='Deducción judicial registrada.'), 201
    except ValueError as error:
        conn.rollback()
        return jsonify(error=str(error)), 400
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/incidentes', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def incidentes_laborales():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'GET':
            execute_sp(
                cursor,
                'rrhh.sp_ListarIncidentesLaborales',
                fallback_sql=(
                    "SELECT i.ID, i.EmpleadoID, e.NombreCompleto, i.TipoIncidente, i.Gravedad, i.Descripcion, "
                    "i.FechaIncidente, i.NotificadoMITRAB, i.AccionesCorrectivas "
                    "FROM IncidentesLaborales i JOIN Empleados e ON e.ID=i.EmpleadoID ORDER BY i.FechaIncidente DESC"
                ),
            )
            return jsonify([{
                'id': row.ID, 'empleado_id': row.EmpleadoID, 'empleado': row.NombreCompleto,
                'tipo': row.TipoIncidente, 'gravedad': row.Gravedad, 'descripcion': row.Descripcion,
                'fecha': row.FechaIncidente.isoformat(), 'notificado_mitrab': bool(row.NotificadoMITRAB),
                'acciones_correctivas': row.AccionesCorrectivas
            } for row in cursor.fetchall()])

        data = request.get_json(silent=True) or {}
        empleado_id = positive_int(data.get('empleado_id'), 'Empleado')
        tipo = data.get('tipo')
        gravedad = data.get('gravedad')
        if tipo not in ('Accidente', 'Casi Accidente', 'Enfermedad Ocupacional'):
            raise ValueError('Tipo de incidente inválido.')
        if gravedad not in ('Leve', 'Grave', 'Muy Grave', 'Mortal'):
            raise ValueError('Gravedad inválida.')
        descripcion = required_text(data.get('descripcion'), 'Descripción', 4000)
        fecha = data.get('fecha') or datetime.now().isoformat()
        datetime.fromisoformat(fecha)
        execute_sp(
            cursor,
            'rrhh.sp_VerificarEmpleadoExiste',
            (empleado_id,),
            fallback_sql="SELECT ID FROM Empleados WHERE ID=?",
        )
        if not cursor.fetchone():
            return jsonify(error='Empleado inexistente.'), 400
        notificado = bool(data.get('notificado_mitrab'))
        execute_sp(
            cursor,
            'rrhh.sp_InsertarIncidenteLaboral',
            (
                empleado_id, tipo, gravedad, descripcion, fecha, notificado,
                datetime.now() if notificado else None,
                (data.get('acciones_correctivas') or '').strip()[:4000] or None, current_user.id
            ),
            fallback_sql=(
                "INSERT INTO IncidentesLaborales (EmpleadoID,TipoIncidente,Gravedad,Descripcion,FechaIncidente,NotificadoMITRAB,FechaNotificacionMITRAB,AccionesCorrectivas,RegistradoPor) "
                "VALUES (?,?,?,?,?,?,?,?,?)"
            ),
        )
        conn.commit()
        return jsonify(status='success', mensaje='Incidente laboral registrado.'), 201
    except ValueError as error:
        conn.rollback()
        return jsonify(error=str(error)), 400
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def obtener_dias_ausentes_auto(cursor, empleado_id, periodo_inicio, periodo_fin, as_of_date=None):
    inicio, fin = as_date(periodo_inicio), as_date(periodo_fin)
    if fin < inicio:
        raise ValueError('El período final no puede ser anterior al inicial.')
    cutoff = business_now().date() if as_of_date is None else as_date(as_of_date)
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerFechasIngresoEgresoEmpleado',
        (empleado_id,),
        fallback_sql="SELECT FechaIngreso, FechaEgreso FROM Empleados WHERE ID = ?",
    )
    empleado = cursor.fetchone()
    if not empleado:
        raise ValueError('Empleado inexistente.')
    inicio = max(inicio, as_date(empleado.FechaIngreso))
    if empleado.FechaEgreso:
        fin = min(fin, as_date(empleado.FechaEgreso))
    fin = min(fin, cutoff)
    if fin < inicio:
        return 0
    # Conservar la salvaguarda cuando la empresa no utilizó el módulo ese mes.
    execute_sp(
        cursor,
        'rrhh.sp_ContarAsistenciasRango',
        (periodo_inicio, periodo_fin),
        fallback_sql="SELECT COUNT(*) FROM Asistencia WHERE Fecha BETWEEN ? AND ?",
    )
    if cursor.fetchone()[0] == 0:
        return 0
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerFechasAsistidasEmpleado',
        (empleado_id, inicio, fin),
        fallback_sql="SELECT DISTINCT Fecha FROM Asistencia WHERE EmpleadoID = ? AND Fecha BETWEEN ? AND ? AND HoraEntrada IS NOT NULL",
    )
    asistidas = [as_date(row.Fecha) for row in cursor.fetchall()]
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerLicenciasSolapadasEmpleado',
        (empleado_id, fin, inicio),
        fallback_sql=(
            "SELECT FechaInicio, FechaFin, TipoLicencia FROM LicenciasEmpleados "
            "WHERE EmpleadoID = ? AND FechaInicio <= ? AND FechaFin >= ?"
        ),
    )
    return len(absent_dates(inicio, fin, asistidas, cursor.fetchall(), as_of_date=cutoff))




def _es_feriado_nacional_ni(d: date) -> bool:
    """Identifica feriados nacionales de descanso obligatorio conforme al Art. 66 del Código del Trabajo de Nicaragua."""
    if (d.month, d.day) in [(1, 1), (5, 1), (7, 19), (9, 14), (9, 15), (12, 8), (12, 25)]:
        return True
    y = d.year
    a = y % 19
    b = y // 100
    c = y % 100
    d_div = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d_div - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    domingo_pascua = date(y, month, day)
    return d == domingo_pascua - timedelta(days=3) or d == domingo_pascua - timedelta(days=2)


@admin_bp.route('/api/rrhh/nomina/precargar_datos', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def precargar_datos_nomina_individual():
    """Calcula y devuelve automáticamente horas extras, feriados trabajados, ausencias, préstamos y cobros por pérdidas."""
    empleado_id = request.args.get('empleado_id', type=int)
    inicio_str = request.args.get('periodo_inicio')
    fin_str = request.args.get('periodo_fin')

    if not empleado_id or not inicio_str or not fin_str:
        return jsonify({'error': 'Parámetros empleado_id, periodo_inicio y periodo_fin son requeridos.'}), 400

    try:
        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fin = datetime.strptime(fin_str, '%Y-%m-%d').date()
    except Exception:
        return jsonify({'error': 'Formato de fecha inválido. Utilice YYYY-MM-DD.'}), 400

    if fin < inicio:
        return jsonify({'error': 'El período final no puede ser anterior al inicial.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerEmpleadoActivoCompleto',
            (empleado_id,),
            fallback_sql="SELECT ID, NombreCompleto, Cargo, SalarioBase, FechaIngreso FROM Empleados WHERE ID = ? AND EstadoEmpleado = 'Activo'"
        )
        emp = cursor.fetchone()
        if not emp:
            return jsonify({'error': 'Empleado no encontrado o inactivo.'}), 404

        salario_base = float(emp.SalarioBase)
        salario_diario = salario_base / 30.0

        # 1. Días Ausentes automáticos
        try:
            dias_ausentes = obtener_dias_ausentes_auto(cursor, empleado_id, inicio, fin)
        except Exception:
            dias_ausentes = 0

        # 2. Préstamos activos
        execute_sp(
            cursor,
            'rrhh.sp_ListarPrestamosActivosEmpleado',
            (empleado_id,),
            fallback_sql="SELECT ID, MontoTotal, CuotaMensual, SaldoPendiente, Motivo FROM PrestamosEmpleados WHERE EmpleadoID = ? AND Estado = 'Activo' AND SaldoPendiente > 0"
        )
        prestamos_rows = cursor.fetchall() or []
        cuota_prestamos = sum(float(min(p.CuotaMensual, p.SaldoPendiente)) for p in prestamos_rows)
        prestamos_info = [{
            'id': p.ID,
            'cuota': float(p.CuotaMensual),
            'saldo': float(p.SaldoPendiente),
            'motivo': getattr(p, 'Motivo', '')
        } for p in prestamos_rows]

        # 3. Cobros por pérdidas pendientes
        execute_sp(
            cursor,
            'rrhh.sp_ListarCobrosPerdidasPendientesEmpleado',
            (empleado_id,),
            fallback_sql="SELECT ID, Descripcion, MontoTotal, SaldoPendiente FROM CobrosPerdidasEmpleados WHERE EmpleadoID = ? AND Estado = 'Pendiente' AND SaldoPendiente > 0"
        )
        perdidas_rows = cursor.fetchall() or []
        saldo_perdidas = sum(float(p.SaldoPendiente) for p in perdidas_rows)
        cuota_perdidas = min(saldo_perdidas, round(salario_base * 0.10, 2))
        perdidas_info = [{
            'id': p.ID,
            'descripcion': p.Descripcion,
            'saldo': float(p.SaldoPendiente)
        } for p in perdidas_rows]

        # 4. Asistencia: Horas Extras y Feriados Trabajados
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaConTurnoPorEmpleadoRango',
            (empleado_id, str(inicio), str(fin)),
            fallback_sql="""
                SELECT a.Fecha, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada,
                       t.HoraEntrada AS TurnoEntrada, t.HoraSalida AS TurnoSalida
                FROM Asistencia a
                LEFT JOIN TurnosLaborales t ON a.TurnoID = t.ID
                WHERE a.EmpleadoID = ? AND a.Fecha >= ? AND a.Fecha <= ?
            """
        )
        asistencias = cursor.fetchall() or []
        horas_extras = 0.0
        feriados_trabajados = 0

        for r in asistencias:
            f = as_date(r.Fecha)
            if _es_feriado_nacional_ni(f):
                feriados_trabajados += 1

            if r.HoraEntrada and r.HoraSalida:
                try:
                    dt_in = datetime.combine(f, r.HoraEntrada)
                    dt_out = datetime.combine(f, r.HoraSalida)
                    if dt_out < dt_in:
                        dt_out += timedelta(days=1)
                    hrs_trabajadas = (dt_out - dt_in).total_seconds() / 3600.0

                    turno_duracion = 8.0
                    if getattr(r, 'TurnoSalida', None) and getattr(r, 'TurnoEntrada', None):
                        s_in = datetime.combine(f, r.TurnoEntrada)
                        s_out = datetime.combine(f, r.TurnoSalida)
                        if s_out < s_in:
                            s_out += timedelta(days=1)
                        turno_duracion = (s_out - s_in).total_seconds() / 3600.0

                    he = max(0.0, hrs_trabajadas - turno_duracion)
                    horas_extras += he
                except Exception:
                    pass

        # 5. Sueldo extraordinario sugerido por feriados trabajados
        sueldo_extraordinario = round(feriados_trabajados * salario_diario, 2)

        return jsonify({
            'status': 'success',
            'empleado': {
                'id': emp.ID,
                'nombre': emp.NombreCompleto,
                'cargo': emp.Cargo,
                'salario_base': salario_base,
            },
            'automaticos': {
                'horas_extras': round(horas_extras, 1),
                'feriados_trabajados': feriados_trabajados,
                'dias_ausentes': dias_ausentes,
                'sueldo_extraordinario': sueldo_extraordinario,
                'deduccion_prestamos': round(cuota_prestamos, 2),
                'cobros_perdidas': round(cuota_perdidas, 2),
                'prestamos_info': prestamos_info,
                'perdidas_info': perdidas_info,
            }
        })
    except Exception as e:
        current_app.logger.exception('Error al precargar datos de nómina individual')
        return jsonify({'error': 'Error al precargar datos automáticos de nómina.'}), 500
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/nomina/calcular', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_nomina():
    datos = request.json or {}
    empleado_id = datos.get('empleado_id')
    periodo_inicio = datos.get('periodo_inicio')
    periodo_fin = datos.get('periodo_fin')
    horas_extras = float(amount(datos.get('horas_extras', 0)))
    otros_ingresos = float(amount(datos.get('otros_ingresos', 0)))
    
    dias_ausentes = float(amount(datos.get('dias_ausentes', 0), maximum=31))
    dias_feriados_trabajados = float(amount(datos.get('dias_feriados_trabajados', 0), maximum=31))

    if not all([empleado_id, periodo_inicio, periodo_fin]):
        return jsonify({'error': 'Faltan datos del período'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        validar_periodo_nomina(cursor, empleado_id, periodo_inicio, periodo_fin)
        if 'dias_ausentes' not in datos:
            dias_ausentes = obtener_dias_ausentes_auto(cursor, empleado_id, periodo_inicio, periodo_fin)
            
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerEmpleadoActivoCompleto',
            (int(empleado_id),),
            fallback_sql="SELECT * FROM Empleados WHERE ID = ? AND EstadoEmpleado = 'Activo'",
        )
        emp = cursor.fetchone()
        if not emp:
            return jsonify({'error': 'Empleado no encontrado o inactivo'}), 404

        salario_base = float(emp.SalarioBase)
        salario_diario = salario_base / 30

        execute_sp(
            cursor,
            'seguridad.sp_ObtenerTasasLaboralesConfig',
            fallback_sql="SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')",
        )
        config = {r.Clave: r.Valor for r in cursor.fetchall()}

        tasa_inss_laboral = float(config.get('inss_laboral', '7.00'))

        execute_sp(
            cursor,
            'rrhh.sp_ContarEmpleadosActivos',
            fallback_sql="SELECT COUNT(*) FROM Empleados WHERE EstadoEmpleado = 'Activo'",
        )
        total_empleados = cursor.fetchone()[0]
        tasa_inss_patronal = float(config.get('inss_patronal_mas50', '22.50')) if total_empleados >= 50 else float(config.get('inss_patronal_menos50', '21.50'))
        tasa_inatec = float(config.get('inatec', '2.00'))

        hora_ordinaria = salario_diario / 8
        monto_horas_extras = horas_extras * hora_ordinaria * 2
        monto_feriados = dias_feriados_trabajados * salario_diario
        monto_ausencias = dias_ausentes * salario_diario * 1.1667
        salario_base_efectivo = max(0.0, salario_base - monto_ausencias)

        # Campos Parte 1: Ingresos adicionales salariales y no salariales
        incentivos = float(amount(datos.get('incentivos', 0)))
        sueldo_extraordinario = float(amount(datos.get('sueldo_extraordinario', monto_feriados)))
        riesgo_laboral = float(amount(datos.get('riesgo_laboral', 0)))
        viaticos = float(amount(datos.get('viaticos', 0)))
        depreciacion_vehiculo = float(amount(datos.get('depreciacion_vehiculo', 0)))

        total_devengado_salarial = salario_base_efectivo + monto_horas_extras + sueldo_extraordinario + incentivos + riesgo_laboral + otros_ingresos
        if total_devengado_salarial <= 0:
            raise ValueError('Revise las ausencias: no hay salario devengado para contabilizar.')

        inss_laboral = total_devengado_salarial * (tasa_inss_laboral / 100)

        # IR Ley 822 acumulado
        periodo_fin_dt = as_date(periodo_fin)
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerHistoricoRentaAnualEmpleado',
            (int(empleado_id), periodo_fin_dt.year, periodo_fin_dt.month),
            fallback_sql="""
                SELECT
                    ISNULL(SUM(TotalDevengado - INSSLaboral), 0) AS RentaGravableAcumulada,
                    ISNULL(SUM(IRMensual), 0) AS IRRetenidoAcumulado,
                    COUNT(*) AS MesesCalculados
                FROM Nomina
                WHERE EmpleadoID = ? AND YEAR(PeriodoFin) = ? AND MONTH(PeriodoFin) < ?
                  AND Estado IN ('Contabilizada', 'Pagada')
            """
        )
        hist_ir = cursor.fetchone()
        acum_gravable = float(hist_ir[0] or 0) if hist_ir else 0.0
        ir_acum = float(hist_ir[1] or 0) if hist_ir else 0.0

        if acum_gravable > 0 or (hist_ir and hist_ir[2] > 0):
            from app.services.payroll_engine import calcular_ir_metodo_acumulado
            gravable_mes = total_devengado_salarial - inss_laboral
            ir_mensual = float(calcular_ir_metodo_acumulado(gravable_mes, acum_gravable, ir_acum, periodo_fin_dt.month))
            renta_neta_anual = (acum_gravable + gravable_mes) / periodo_fin_dt.month * 12
        else:
            renta_neta_mensual = total_devengado_salarial - inss_laboral
            renta_neta_anual = renta_neta_mensual * 12
            ir_anual = 0
            tabla_ir = json.loads(config.get('ir_tabla', '[]'))
            for estrato in tabla_ir:
                if renta_neta_anual >= estrato['desde'] and renta_neta_anual <= estrato['hasta']:
                    ir_anual = ((renta_neta_anual - estrato['exceso']) * estrato['tasa'] / 100) + estrato['base']
                    break
            ir_mensual = ir_anual / 12

        salario_neto_pre = total_devengado_salarial - inss_laboral - ir_mensual
        pension_alimenticia = calcular_deducciones_judiciales(
            cursor, int(empleado_id), salario_neto_pre, periodo_fin
        )

        neto_disponible_vales = max(Decimal('0.00'), amount(total_devengado_salarial) - amount(inss_laboral) - amount(ir_mensual) - amount(pension_alimenticia))
        vales_descontados = _calcular_y_aplicar_vales_periodo(
            cursor, getattr(emp, 'UsuarioID', None), periodo_fin, neto_disponible_vales
        )

        # Parte 2: Deducciones por préstamos y cobro por pérdidas
        neto_disponible_prestamos = max(Decimal('0.00'), neto_disponible_vales - vales_descontados)
        prestamos_rows = []
        if 'deduccion_prestamo' in datos:
            deduccion_prestamos = min(amount(datos['deduccion_prestamo']), neto_disponible_prestamos)
        else:
            execute_sp(
                cursor,
                'rrhh.sp_ListarPrestamosActivosEmpleado',
                (int(empleado_id),),
                fallback_sql="SELECT ID, MontoTotal, CuotaMensual, SaldoPendiente FROM PrestamosEmpleados WHERE EmpleadoID = ? AND Estado = 'Activo' AND SaldoPendiente > 0"
            )
            prestamos_rows = cursor.fetchall() or []
            cuota_prestamos_total = sum(min(Decimal(str(p.CuotaMensual)), Decimal(str(p.SaldoPendiente))) for p in prestamos_rows)
            deduccion_prestamos = min(cuota_prestamos_total, neto_disponible_prestamos)

        neto_disponible_perdidas = max(Decimal('0.00'), neto_disponible_prestamos - deduccion_prestamos)
        perdidas_rows = []
        tope_perdidas = round(amount(total_devengado_salarial) * Decimal('0.10'), 2)
        if 'cobro_perdida' in datos:
            cobros_perdidas = min(amount(datos['cobro_perdida']), neto_disponible_perdidas, tope_perdidas)
        else:
            execute_sp(
                cursor,
                'rrhh.sp_ListarCobrosPerdidasPendientesEmpleado',
                (int(empleado_id),),
                fallback_sql="SELECT ID, Descripcion, MontoTotal, SaldoPendiente FROM CobrosPerdidasEmpleados WHERE EmpleadoID = ? AND Estado = 'Pendiente' AND SaldoPendiente > 0"
            )
            perdidas_rows = cursor.fetchall() or []
            cuota_perdidas_total = sum(Decimal(str(getattr(p, 'SaldoPendiente', 0))) for p in perdidas_rows)
            cobros_perdidas = min(cuota_perdidas_total, neto_disponible_perdidas, tope_perdidas)

        total_ingresos = amount(total_devengado_salarial) + amount(viaticos) + amount(depreciacion_vehiculo)
        total_deducciones = amount(inss_laboral) + amount(ir_mensual) + amount(pension_alimenticia) + amount(vales_descontados) + amount(deduccion_prestamos) + amount(cobros_perdidas)
        salario_neto = amount(max(Decimal('0.00'), total_ingresos - total_deducciones), 'Salario neto')

        # Parte 3: Provisiones y cargas patronales
        inss_patronal = round(amount(total_devengado_salarial) * Decimal(str(tasa_inss_patronal)) / Decimal('100'), 2)
        inatec = round(amount(total_devengado_salarial) * Decimal(str(tasa_inatec)) / Decimal('100'), 2)
        provision_vacaciones = round(amount(total_devengado_salarial) * Decimal('2.5') / Decimal('30'), 2)
        provision_aguinaldo = round(amount(total_devengado_salarial) / Decimal('12'), 2)

        fecha_ingreso = as_date(emp.FechaIngreso)
        anios_antiguedad = max(0.0, (periodo_fin_dt - fecha_ingreso).days / 365.25)
        tasa_indem = calcular_tasa_provision_indemnizacion(anios_antiguedad)
        provision_indemnizacion = round(amount(total_devengado_salarial) * tasa_indem, 2)
        total_patronal = inss_patronal + inatec + provision_vacaciones + provision_aguinaldo + provision_indemnizacion
        costo_total_empresa = total_ingresos + total_patronal

        # Métricas de asistencia
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerMetricasAsistenciaPeriodo',
            (int(empleado_id), periodo_inicio, periodo_fin),
            fallback_sql="""
                SELECT
                    COUNT(*) AS TotalAsistencias,
                    SUM(CASE WHEN EstadoEntrada = 'A Tiempo' OR EstadoEntrada = 'Puntual' THEN 1 ELSE 0 END) AS Puntuales,
                    SUM(CASE WHEN EstadoEntrada = 'Llegada Tardia' OR EstadoEntrada = 'Tarde' THEN 1 ELSE 0 END) AS Tardanzas
                FROM Asistencia
                WHERE EmpleadoID = ? AND Fecha >= ? AND Fecha <= ?
            """
        )
        att_row = cursor.fetchone()
        tot_asist = att_row[0] if att_row else 0
        puntuales = att_row[1] if att_row and att_row[1] is not None else 0
        promedio_asistencia = min(100.0, round((tot_asist / 30.0) * 100.0, 2)) if tot_asist > 0 else (100.0 if dias_ausentes == 0 else max(0.0, round(((30.0 - dias_ausentes) / 30.0) * 100.0, 2)))
        promedio_puntualidad = round((puntuales / tot_asist) * 100.0, 2) if tot_asist > 0 else 100.0

        execute_sp(
            cursor,
            'rrhh.sp_InsertarNominaMensual',
            (
                int(empleado_id), periodo_inicio, periodo_fin, float(salario_base_efectivo),
                horas_extras, float(monto_horas_extras), float(otros_ingresos + sueldo_extraordinario), float(total_devengado_salarial),
                float(inss_laboral), float(ir_mensual), float(pension_alimenticia), float(vales_descontados),
                float(total_deducciones), float(salario_neto), float(inss_patronal), float(inatec), current_user.id
            ),
            fallback_sql="""
            INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Contabilizada', ?)
        """,
        )
        nomina_id = cursor.fetchone()[0]

        # Actualizar campos estructurados en rrhh.Nomina
        execute_sp(
            cursor,
            'rrhh.sp_ActualizarNominaEstructurada',
            (
                nomina_id,
                float(viaticos),
                float(depreciacion_vehiculo),
                float(incentivos),
                float(riesgo_laboral),
                float(sueldo_extraordinario),
                float(deduccion_prestamos),
                float(cobros_perdidas),
                float(provision_vacaciones),
                float(provision_aguinaldo),
                float(provision_indemnizacion),
                float(costo_total_empresa),
                float(promedio_asistencia),
                float(promedio_puntualidad),
            ),
            fallback_sql="""
                UPDATE Nomina SET
                    Viaticos = ?, DepreciacionVehiculo = ?, Incentivos = ?, RiesgoLaboral = ?,
                    SueldoExtraordinario = ?, PrestamosDescontados = ?, CobrosPerdidas = ?,
                    ProvisionVacaciones = ?, ProvisionAguinaldo = ?, ProvisionIndemnizacion = ?,
                    CostoTotalEmpresa = ?, PromedioAsistencia = ?, PromedioPuntualidad = ?
                WHERE ID = ?
            """
        )

        # Detalle de ingresos
        execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Sueldo Base Efectivo', 'Ingreso', float(salario_base_efectivo), 'Salario ordinario ajustado por ausencias'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if monto_horas_extras > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'Horas Extras ({horas_extras}h)', 'Ingreso', float(monto_horas_extras), 'Horas extras al 100%'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if sueldo_extraordinario > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Sueldo Extraordinario', 'Ingreso', float(sueldo_extraordinario), 'Feriados o descanso trabajado al doble'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if incentivos > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Incentivos', 'Ingreso', float(incentivos), 'Bonificaciones por productividad'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if riesgo_laboral > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Riesgo Laboral 1.5%', 'Ingreso', float(riesgo_laboral), 'Compensación por riesgo de puesto'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if otros_ingresos > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Otros Ingresos', 'Ingreso', float(otros_ingresos), 'Ingresos varios'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if viaticos > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Viáticos', 'Ingreso', float(viaticos), 'No salarial / rendición de gastos'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
        if depreciacion_vehiculo > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Depreciación de Vehículo', 'Ingreso', float(depreciacion_vehiculo), 'No salarial / depreciación herramienta trabajo'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")

        # Detalle de deducciones
        if float(inss_laboral) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INSS Laboral ({tasa_inss_laboral}%)', 'Deduccion', float(inss_laboral), 'Aporte de seguridad social'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
        if float(ir_mensual) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'IR Laboral Ley 822', 'Deduccion', float(ir_mensual), 'Retención progresiva'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
        if float(pension_alimenticia) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Pensión Alimenticia / Embargo', 'Deduccion', float(pension_alimenticia), 'Orden judicial'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
        if float(vales_descontados) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Vales / Adelantos Descontados', 'Deduccion', float(vales_descontados), 'Anticipos recibidos en el período'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
        if float(deduccion_prestamos) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Deducción por Préstamos', 'Deduccion', float(deduccion_prestamos), 'Amortización cuota de préstamo'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
        if float(cobros_perdidas) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Cobro por Pérdidas', 'Deduccion', float(cobros_perdidas), 'Recuperación autorizada por mermas/pérdidas'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")

        # Detalle de cargas y provisiones patronales
        if float(inss_patronal) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INSS Patronal ({tasa_inss_patronal}%)', 'Patronal', float(inss_patronal), 'Aporte patronal INSS'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
        if float(inatec) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INATEC ({tasa_inatec}%)', 'Patronal', float(inatec), 'Aporte patronal capacitación'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
        if float(provision_vacaciones) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Vacaciones (8.33%)', 'Patronal', float(provision_vacaciones), '2.5 días por mes trabajado'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
        if float(provision_aguinaldo) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Aguinaldo (8.33%)', 'Patronal', float(provision_aguinaldo), '1/12 por mes trabajado'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
        if float(provision_indemnizacion) > 0:
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Indemnización', 'Patronal', float(provision_indemnizacion), 'Indemnización por antigüedad'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")

        # Registrar abonos a préstamos
        if prestamos_rows and deduccion_prestamos > 0:
            restante_abono = float(deduccion_prestamos)
            for pr in prestamos_rows:
                if restante_abono <= 0: break
                abono = min(float(pr.CuotaMensual), float(pr.SaldoPendiente), restante_abono)
                if abono > 0:
                    execute_sp(cursor, 'rrhh.sp_RegistrarAbonoPrestamo', (pr.ID, abono), fallback_sql="UPDATE PrestamosEmpleados SET SaldoPendiente = CASE WHEN SaldoPendiente <= ? THEN 0 ELSE SaldoPendiente - ? END WHERE ID = ?")
                    restante_abono -= abono

        # Registrar deducciones por pérdidas
        if perdidas_rows and cobros_perdidas > 0:
            restante_cobro = float(cobros_perdidas)
            for pd in perdidas_rows:
                if restante_cobro <= 0: break
                desc = min(float(getattr(pd, 'SaldoPendiente', 0)), restante_cobro)
                if desc > 0:
                    execute_sp(cursor, 'rrhh.sp_RegistrarCobroPerdida', (pd.ID, desc), fallback_sql="UPDATE CobrosPerdidasEmpleados SET SaldoPendiente = CASE WHEN SaldoPendiente <= ? THEN 0 ELSE SaldoPendiente - ? END WHERE ID = ?")
                    restante_cobro -= desc

        _contabilizar_nomina_segura(
            cursor=cursor,
            usuario_id=current_user.id,
            nomina_id=nomina_id,
            empleado_nombre=emp.NombreCompleto,
            salario_bruto=total_devengado_salarial,
            inss_laboral=inss_laboral,
            ir_retenido=ir_mensual,
            inss_patronal=inss_patronal,
            inatec=inatec,
            pension_alimenticia=pension_alimenticia,
            vales_descontados=vales_descontados,
            salario_neto=salario_neto,
            cargo=emp.Cargo,
            ip=request.remote_addr,
            fecha=_fecha_contable_periodo(periodo_fin),
            provision_vacaciones=provision_vacaciones,
            provision_aguinaldo=provision_aguinaldo,
            provision_indemnizacion=provision_indemnizacion,
            deduccion_prestamos=deduccion_prestamos,
            cobro_perdidas=cobros_perdidas,
            viaticos=viaticos,
            depreciacion_vehiculo=depreciacion_vehiculo,
        )

        conn.commit()

        return jsonify({
            'status': 'success',
            'mensaje': 'Nómina calculada correctamente',
            'nomina': {
                'id': nomina_id,
                'empleado': emp.NombreCompleto,
                'salario_base': salario_base,
                'salario_diario': round(salario_diario, 2),
                'horas_extras': horas_extras,
                'monto_horas_extras': round(monto_horas_extras, 2),
                'otros_ingresos': otros_ingresos,
                'total_devengado': round(float(total_devengado_salarial), 2),
                'inss_laboral': round(float(inss_laboral), 2),
                'tasa_inss_laboral': tasa_inss_laboral,
                'ir_mensual': round(float(ir_mensual), 2),
                'renta_neta_anual_proyectada': round(float(renta_neta_anual), 2),
                'pension_alimenticia': round(float(pension_alimenticia), 2),
                'vales_descontados': round(float(vales_descontados), 2),
                'total_deducciones': round(float(total_deducciones), 2),
                'salario_neto': round(float(salario_neto), 2),
                'inss_patronal': round(float(inss_patronal), 2),
                'tasa_inss_patronal': tasa_inss_patronal,
                'inatec': round(float(inatec), 2),
                'total_empleados': total_empleados,
                # Campos Parte 1, 2 y 3
                'viaticos': round(float(viaticos), 2),
                'depreciacion_vehiculo': round(float(depreciacion_vehiculo), 2),
                'incentivos': round(float(incentivos), 2),
                'riesgo_laboral': round(float(riesgo_laboral), 2),
                'sueldo_extraordinario': round(float(sueldo_extraordinario), 2),
                'deduccion_prestamos': round(float(deduccion_prestamos), 2),
                'cobros_perdidas': round(float(cobros_perdidas), 2),
                'provision_vacaciones': round(float(provision_vacaciones), 2),
                'provision_aguinaldo': round(float(provision_aguinaldo), 2),
                'provision_indemnizacion': round(float(provision_indemnizacion), 2),
                'costo_total_empresa': round(float(costo_total_empresa), 2),
                'promedio_asistencia_pct': float(promedio_asistencia),
                'promedio_puntualidad_pct': float(promedio_puntualidad),
            }
        })
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

def _obtener_liquidacion(cursor, empleado, fecha_egreso, motivo):
    fecha_salida = as_date(fecha_egreso)
    if fecha_salida < as_date(empleado.FechaIngreso):
        raise ValueError('La fecha de egreso no puede ser anterior al ingreso.')
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerUltimos6SalariosNomina',
        (empleado.ID,),
        fallback_sql="SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? ORDER BY PeriodoFin DESC",
    )
    salarios = [float(row.SalarioBruto) for row in cursor.fetchall()]
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerVacacionesEmpleadoRango',
        (empleado.ID, fecha_salida, as_date(empleado.FechaIngreso)),
        fallback_sql=(
            "SELECT FechaInicio, FechaFin, TipoLicencia, DiasOtorgados FROM LicenciasEmpleados "
            "WHERE EmpleadoID = ? AND TipoLicencia = 'Vacaciones' AND FechaInicio <= ? AND FechaFin >= ?"
        ),
    )
    return liquidation(empleado, fecha_salida, motivo, salarios, cursor.fetchall())


@admin_bp.route('/api/rrhh/liquidacion/calcular', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_liquidacion():
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict):
        return jsonify(error='Datos inválidos'), 400
    empleado_id, fecha_egreso = datos.get('empleado_id'), datos.get('fecha_egreso')
    motivo = datos.get('motivo', 'Renuncia Voluntaria')
    if not all([empleado_id, fecha_egreso]):
        return jsonify(error='Faltan datos'), 400
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerEmpleadoCompletoPorID',
            (int(empleado_id),),
            fallback_sql="SELECT * FROM Empleados WHERE ID = ?",
        )
        empleado = cursor.fetchone()
        if not empleado:
            return jsonify(error='Empleado no encontrado'), 404
        return jsonify(status='success', liquidacion=_obtener_liquidacion(cursor, empleado, fecha_egreso, motivo))
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    except Exception:
        current_app.logger.exception('Error al calcular liquidación')
        return jsonify(error='Error interno del servidor al procesar la solicitud.'), 500
    finally:
        conn.close()


@admin_bp.route('/rrhh/liquidacion/reporte', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def reporte_liquidacion():
    empleado_id, fecha_egreso = request.args.get('empleado_id'), request.args.get('fecha_egreso')
    motivo = request.args.get('motivo', 'Renuncia Voluntaria')
    if not all([empleado_id, fecha_egreso]):
        flash('Faltan datos para generar el reporte.', 'error')
        return redirect(url_for('admin.rrhh'))
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerEmpleadoCompletoPorID',
            (int(empleado_id),),
            fallback_sql="SELECT * FROM Empleados WHERE ID = ?",
        )
        empleado = cursor.fetchone()
        if not empleado:
            flash('Empleado no encontrado', 'error')
            return redirect(url_for('admin.rrhh'))
        data = _obtener_liquidacion(cursor, empleado, fecha_egreso, motivo)
        return render_template('admin/colilla_liquidacion.html', liquidacion=data, emp=empleado, datetime=datetime)
    except (ValueError, TypeError) as error:
        flash(str(error), 'error')
        return redirect(url_for('admin.rrhh'))
    except Exception:
        current_app.logger.exception('Error al generar reporte de liquidación')
        flash('Error interno al generar el reporte.', 'error')
        return redirect(url_for('admin.rrhh'))
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/nomina/calcular_batch', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_nomina_batch():
    datos = request.json or {}
    periodo_inicio = datos.get('periodo_inicio')
    periodo_fin = datos.get('periodo_fin')
    
    if not all([periodo_inicio, periodo_fin]):
        return jsonify({'error': 'Faltan datos del período'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        execute_sp(
            cursor,
            'seguridad.sp_ObtenerTasasLaboralesConfig',
            fallback_sql="SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')",
        )
        config = {r.Clave: r.Valor for r in cursor.fetchall()}
        
        tasa_inss_laboral = float(config.get('inss_laboral', '7.00'))
        tasa_inatec = float(config.get('inatec', '2.00'))
        tabla_ir = json.loads(config.get('ir_tabla', '[]'))
        
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosCompletos',
            fallback_sql="SELECT * FROM Empleados WHERE EstadoEmpleado = 'Activo'",
        )
        empleados = cursor.fetchall()
        total_empleados = len(empleados)
        
        if total_empleados == 0:
            return jsonify({'error': 'No hay empleados activos para procesar'}), 400
            
        tasa_inss_patronal = float(config.get('inss_patronal_mas50', '22.50')) if total_empleados >= 50 else float(config.get('inss_patronal_menos50', '21.50'))
        
        nomina_ids = []
        omitidos_contabilizados = 0
        inicio_dt = date.fromisoformat(str(periodo_inicio))
        fin_dt = date.fromisoformat(str(periodo_fin))
        import calendar
        if inicio_dt.day != 1 or fin_dt != date(inicio_dt.year, inicio_dt.month, calendar.monthrange(inicio_dt.year, inicio_dt.month)[1]):
            raise ValueError('El cálculo mensual requiere el primer y último día del mismo mes.')
        if fin_dt < inicio_dt:
            raise ValueError('El período final no puede ser anterior al inicial.')
        _validar_no_periodo_futuro(inicio_dt, fin_dt, aguinaldo=False)

        for emp in empleados:
            execute_sp(
                cursor,
                'rrhh.sp_VerificarNominaExistenteMensual',
                (emp.ID, fin_dt, inicio_dt),
                fallback_sql="SELECT ID, Estado FROM Nomina WHERE EmpleadoID=? AND PeriodoInicio<=? AND PeriodoFin>=? AND SalarioBruto > 0 AND Estado IN ('Contabilizada', 'Pagada')",
            )
            if cursor.fetchone():
                omitidos_contabilizados += 1
                continue
            validar_periodo_nomina(cursor, emp.ID, periodo_inicio, periodo_fin)
            salario_base = float(emp.SalarioBase)
            salario_diario = salario_base / 30
            
            dias_ausentes = obtener_dias_ausentes_auto(cursor, emp.ID, periodo_inicio, periodo_fin)
            monto_ausencias = dias_ausentes * salario_diario * 1.1667
            salario_base_efectivo = max(0.0, salario_base - monto_ausencias)
            
            total_devengado_salarial = salario_base_efectivo
            if total_devengado_salarial <= 0:
                raise ValueError(f'Revise las ausencias de {emp.NombreCompleto}: no hay salario devengado.')
            
            inss_laboral = total_devengado_salarial * (tasa_inss_laboral / 100)
            
            # IR Ley 822 acumulado
            execute_sp(
                cursor,
                'rrhh.sp_ObtenerHistoricoRentaAnualEmpleado',
                (emp.ID, fin_dt.year, fin_dt.month),
                fallback_sql="""
                    SELECT
                        ISNULL(SUM(TotalDevengado - INSSLaboral), 0) AS RentaGravableAcumulada,
                        ISNULL(SUM(IRMensual), 0) AS IRRetenidoAcumulado,
                        COUNT(*) AS MesesCalculados
                    FROM Nomina
                    WHERE EmpleadoID = ? AND YEAR(PeriodoFin) = ? AND MONTH(PeriodoFin) < ?
                      AND Estado IN ('Contabilizada', 'Pagada')
                """
            )
            hist_ir = cursor.fetchone()
            acum_gravable = float(hist_ir[0] or 0) if hist_ir else 0.0
            ir_acum = float(hist_ir[1] or 0) if hist_ir else 0.0

            if acum_gravable > 0 or (hist_ir and hist_ir[2] > 0):
                from app.services.payroll_engine import calcular_ir_metodo_acumulado
                gravable_mes = total_devengado_salarial - inss_laboral
                ir_mensual = float(calcular_ir_metodo_acumulado(gravable_mes, acum_gravable, ir_acum, fin_dt.month))
            else:
                renta_neta_anual = (total_devengado_salarial - inss_laboral) * 12
                ir_anual = 0
                for estrato in tabla_ir:
                    if renta_neta_anual >= estrato['desde'] and renta_neta_anual <= estrato['hasta']:
                        ir_anual = ((renta_neta_anual - estrato['exceso']) * estrato['tasa'] / 100) + estrato['base']
                        break
                ir_mensual = ir_anual / 12
            
            salario_neto_pre = total_devengado_salarial - inss_laboral - ir_mensual
            pension_alimenticia = calcular_deducciones_judiciales(
                cursor, emp.ID, salario_neto_pre, periodo_fin
            )
            
            neto_disponible_vales = max(Decimal('0.00'), amount(total_devengado_salarial) - amount(inss_laboral) - amount(ir_mensual) - amount(pension_alimenticia))
            vales_descontados = _calcular_y_aplicar_vales_periodo(
                cursor, getattr(emp, 'UsuarioID', None), periodo_fin, neto_disponible_vales
            )

            # Préstamos activos del empleado
            neto_disponible_prestamos = max(Decimal('0.00'), neto_disponible_vales - vales_descontados)
            execute_sp(
                cursor,
                'rrhh.sp_ListarPrestamosActivosEmpleado',
                (emp.ID,),
                fallback_sql="SELECT ID, MontoTotal, CuotaMensual, SaldoPendiente FROM PrestamosEmpleados WHERE EmpleadoID = ? AND Estado = 'Activo' AND SaldoPendiente > 0"
            )
            prestamos_rows = cursor.fetchall() or []
            cuota_prestamos_total = sum(min(Decimal(str(p.CuotaMensual)), Decimal(str(p.SaldoPendiente))) for p in prestamos_rows)
            deduccion_prestamos = min(cuota_prestamos_total, neto_disponible_prestamos)

            # Cobros por pérdidas pendientes
            neto_disponible_perdidas = max(Decimal('0.00'), neto_disponible_prestamos - deduccion_prestamos)
            tope_perdidas = round(amount(total_devengado_salarial) * Decimal('0.10'), 2)
            execute_sp(
                cursor,
                'rrhh.sp_ListarCobrosPerdidasPendientesEmpleado',
                (emp.ID,),
                fallback_sql="SELECT ID, Descripcion, MontoTotal, SaldoPendiente FROM CobrosPerdidasEmpleados WHERE EmpleadoID = ? AND Estado = 'Pendiente' AND SaldoPendiente > 0"
            )
            perdidas_rows = cursor.fetchall() or []
            cuota_perdidas_total = sum(Decimal(str(getattr(p, 'SaldoPendiente', 0))) for p in perdidas_rows)
            cobros_perdidas = min(cuota_perdidas_total, neto_disponible_perdidas, tope_perdidas)

            total_deducciones = amount(inss_laboral) + amount(ir_mensual) + amount(pension_alimenticia) + amount(vales_descontados) + amount(deduccion_prestamos) + amount(cobros_perdidas)
            salario_neto = amount(max(Decimal('0.00'), amount(total_devengado_salarial) - total_deducciones), 'Salario neto')

            # Provisiones y cargas patronales
            inss_patronal = round(amount(total_devengado_salarial) * Decimal(str(tasa_inss_patronal)) / Decimal('100'), 2)
            inatec = round(amount(total_devengado_salarial) * Decimal(str(tasa_inatec)) / Decimal('100'), 2)
            provision_vacaciones = round(amount(total_devengado_salarial) * Decimal('2.5') / Decimal('30'), 2)
            provision_aguinaldo = round(amount(total_devengado_salarial) / Decimal('12'), 2)

            fecha_ingreso = as_date(emp.FechaIngreso)
            anios_antiguedad = max(0.0, (fin_dt - fecha_ingreso).days / 365.25)
            tasa_indem = calcular_tasa_provision_indemnizacion(anios_antiguedad)
            provision_indemnizacion = round(amount(total_devengado_salarial) * tasa_indem, 2)
            total_patronal = inss_patronal + inatec + provision_vacaciones + provision_aguinaldo + provision_indemnizacion
            costo_total_empresa = amount(total_devengado_salarial) + total_patronal

            # Métricas de asistencia
            promedio_asistencia = 100.0 if dias_ausentes == 0 else max(0.0, round(((30.0 - dias_ausentes) / 30.0) * 100.0, 2))
            promedio_puntualidad = 100.0

            execute_sp(
                cursor,
                'rrhh.sp_InsertarNominaBatch',
                (
                    emp.ID, periodo_inicio, periodo_fin, float(salario_base_efectivo), float(total_devengado_salarial),
                    float(inss_laboral), float(ir_mensual), float(pension_alimenticia), float(vales_descontados),
                    float(total_deducciones), float(salario_neto), float(inss_patronal), float(inatec), current_user.id
                ),
                fallback_sql="""
                INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                    HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                    INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                    TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Contabilizada', ?)
            """,
            )
            nomina_id = cursor.fetchone()[0]
            nomina_ids.append(nomina_id)

            # Actualizar campos extendidos
            execute_sp(
                cursor,
                'rrhh.sp_ActualizarNominaEstructurada',
                (
                    nomina_id, 0.0, 0.0, 0.0, 0.0, 0.0,
                    float(deduccion_prestamos), float(cobros_perdidas),
                    float(provision_vacaciones), float(provision_aguinaldo), float(provision_indemnizacion),
                    float(costo_total_empresa), float(promedio_asistencia), float(promedio_puntualidad),
                ),
                fallback_sql="""
                    UPDATE Nomina SET
                        Viaticos = 0, DepreciacionVehiculo = 0, Incentivos = 0, RiesgoLaboral = 0,
                        SueldoExtraordinario = 0, PrestamosDescontados = ?, CobrosPerdidas = ?,
                        ProvisionVacaciones = ?, ProvisionAguinaldo = ?, ProvisionIndemnizacion = ?,
                        CostoTotalEmpresa = ?, PromedioAsistencia = ?, PromedioPuntualidad = ?
                    WHERE ID = ?
                """
            )

            # Insertar detalle nómina
            execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Sueldo Base Efectivo', 'Ingreso', float(salario_base_efectivo), 'Salario ordinario ajustado'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Ingreso', ?, ?)")
            if float(inss_laboral) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INSS Laboral ({tasa_inss_laboral}%)', 'Deduccion', float(inss_laboral), 'Aporte de seguridad social'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(ir_mensual) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'IR Laboral Ley 822', 'Deduccion', float(ir_mensual), 'Retención progresiva'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(pension_alimenticia) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Pensión Alimenticia / Embargo', 'Deduccion', float(pension_alimenticia), 'Orden judicial'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(vales_descontados) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Vales / Adelantos Descontados', 'Deduccion', float(vales_descontados), 'Anticipos recibidos'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(deduccion_prestamos) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Deducción por Préstamos', 'Deduccion', float(deduccion_prestamos), 'Amortización préstamo'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(cobros_perdidas) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Cobro por Pérdidas', 'Deduccion', float(cobros_perdidas), 'Recuperación autorizada'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Deduccion', ?, ?)")
            if float(inss_patronal) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INSS Patronal ({tasa_inss_patronal}%)', 'Patronal', float(inss_patronal), 'Aporte patronal INSS'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
            if float(inatec) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, f'INATEC ({tasa_inatec}%)', 'Patronal', float(inatec), 'Aporte patronal capacitación'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
            if float(provision_vacaciones) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Vacaciones (8.33%)', 'Patronal', float(provision_vacaciones), '2.5 días por mes trabajado'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
            if float(provision_aguinaldo) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Aguinaldo (8.33%)', 'Patronal', float(provision_aguinaldo), '1/12 por mes trabajado'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")
            if float(provision_indemnizacion) > 0:
                execute_sp(cursor, 'rrhh.sp_InsertarDetalleNomina', (nomina_id, 'Provisión Indemnización', 'Patronal', float(provision_indemnizacion), 'Indemnización por antigüedad'), fallback_sql="INSERT INTO DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion) VALUES (?, ?, 'Patronal', ?, ?)")

            # Registrar abonos
            if prestamos_rows and deduccion_prestamos > 0:
                restante_abono = float(deduccion_prestamos)
                for pr in prestamos_rows:
                    if restante_abono <= 0: break
                    abono = min(float(pr.CuotaMensual), float(pr.SaldoPendiente), restante_abono)
                    if abono > 0:
                        execute_sp(cursor, 'rrhh.sp_RegistrarAbonoPrestamo', (pr.ID, abono), fallback_sql="UPDATE PrestamosEmpleados SET SaldoPendiente = CASE WHEN SaldoPendiente <= ? THEN 0 ELSE SaldoPendiente - ? END WHERE ID = ?")
                        restante_abono -= abono

            if perdidas_rows and cobros_perdidas > 0:
                restante_cobro = float(cobros_perdidas)
                for pd in perdidas_rows:
                    if restante_cobro <= 0: break
                    desc = min(float(getattr(pd, 'SaldoPendiente', 0)), restante_cobro)
                    if desc > 0:
                        execute_sp(cursor, 'rrhh.sp_RegistrarCobroPerdida', (pd.ID, desc), fallback_sql="UPDATE CobrosPerdidasEmpleados SET SaldoPendiente = CASE WHEN SaldoPendiente <= ? THEN 0 ELSE SaldoPendiente - ? END WHERE ID = ?")
                        restante_cobro -= desc

            _contabilizar_nomina_segura(
                cursor=cursor,
                usuario_id=current_user.id,
                nomina_id=nomina_id,
                empleado_nombre=emp.NombreCompleto,
                salario_bruto=total_devengado_salarial,
                inss_laboral=inss_laboral,
                ir_retenido=ir_mensual,
                inss_patronal=inss_patronal,
                inatec=inatec,
                pension_alimenticia=pension_alimenticia,
                vales_descontados=vales_descontados,
                salario_neto=salario_neto,
                cargo=emp.Cargo,
                ip=request.remote_addr,
                fecha=_fecha_contable_periodo(periodo_fin),
                provision_vacaciones=provision_vacaciones,
                provision_aguinaldo=provision_aguinaldo,
                provision_indemnizacion=provision_indemnizacion,
                deduccion_prestamos=deduccion_prestamos,
                cobro_perdidas=cobros_perdidas,
                viaticos=0,
                depreciacion_vehiculo=0,
            )

        if not nomina_ids and omitidos_contabilizados > 0:
            raise ValueError('Todos los empleados activos ya tienen su planilla generada y contabilizada para este período.')

        conn.commit()
        procesados = len(nomina_ids)
        extra = f' ({omitidos_contabilizados} ya estaban contabilizados)' if omitidos_contabilizados else ''
        return jsonify({'status': 'success', 'mensaje': f'Planilla generada y contabilizada para {procesados} empleados{extra}.'})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/aguinaldo/calcular_batch', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_aguinaldo_batch():
    datos = request.json
    anio = int(datos.get('anio', datetime.now().year))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosCompletos',
            fallback_sql="SELECT * FROM Empleados WHERE EstadoEmpleado = 'Activo'",
        )
        empleados = cursor.fetchall()
        total_empleados = len(empleados)
        
        if total_empleados == 0:
            return jsonify({'error': 'No hay empleados activos para procesar'}), 400
            
        fecha_fin_ciclo = date(anio, 11, 30)
        fecha_inicio_ciclo = date(anio - 1, 12, 1)
        generados = 0
        omitidos = 0
        
        for emp in empleados:
            execute_sp(
                cursor,
                'rrhh.sp_VerificarNominaExistenteAguinaldo',
                (emp.ID, fecha_fin_ciclo, fecha_inicio_ciclo),
                fallback_sql="SELECT ID, Estado FROM Nomina WHERE EmpleadoID=? AND PeriodoInicio<=? AND PeriodoFin>=? AND SalarioBruto = 0 AND Estado IN ('Contabilizada', 'Pagada')",
            )
            if cursor.fetchone():
                omitidos += 1
                continue
            validar_periodo_nomina(cursor, emp.ID, fecha_inicio_ciclo, fecha_fin_ciclo, aguinaldo=True)
            fecha_ingreso = emp.FechaIngreso
            if type(fecha_ingreso) is str:
                fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
            elif hasattr(fecha_ingreso, 'date'):
                fecha_ingreso = fecha_ingreso.date()
                
            execute_sp(
                cursor,
                'rrhh.sp_ObtenerUltimos6SalariosHastaFecha',
                (emp.ID, fecha_fin_ciclo.strftime('%Y-%m-%d')),
                fallback_sql="SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? AND PeriodoFin <= ? ORDER BY PeriodoFin DESC",
            )
            nominas_recientes = [float(r.SalarioBruto) for r in cursor.fetchall()]
            salario_base = float(emp.SalarioBase)
            salario_max_6m = max(nominas_recientes) if nominas_recientes else salario_base
            
            inicio_aguinaldo_real = max(fecha_inicio_ciclo, fecha_ingreso)
            
            if inicio_aguinaldo_real <= fecha_fin_ciclo:
                dias_aguinaldo = (fecha_fin_ciclo - inicio_aguinaldo_real).days + 1
                aguinaldo_proporcional = float(amount(salario_max_6m * (dias_aguinaldo / 365.0)))
                
                execute_sp(
                    cursor,
                    'rrhh.sp_InsertarAguinaldoBatch',
                    (
                        emp.ID, fecha_inicio_ciclo.strftime('%Y-%m-%d'), fecha_fin_ciclo.strftime('%Y-%m-%d'),
                        aguinaldo_proporcional, aguinaldo_proporcional, aguinaldo_proporcional, current_user.id
                    ),
                    fallback_sql="""
                    INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                        HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                        INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                        TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?, 0, 0, 0, 0, 0, ?, 0, 0, 'Contabilizada', ?)
                """,
                )
                row_ag = cursor.fetchone()
                nomina_ag_id = row_ag[0] if row_ag else None
                if nomina_ag_id:
                    from app.services.contabilidad_service import ContabilidadService
                    ContabilidadService.contabilizar_aguinaldo(
                        cursor=cursor,
                        usuario_id=current_user.id,
                        nomina_id=nomina_ag_id,
                        empleado_nombre=emp.NombreCompleto,
                        monto_aguinaldo=aguinaldo_proporcional,
                        cargo=emp.Cargo,
                        ip=request.remote_addr,
                        fecha=_fecha_contable_periodo(fecha_fin_ciclo)
                    )
                generados += 1

        if generados == 0 and omitidos > 0:
            raise ValueError('La planilla de Aguinaldo ya fue generada y contabilizada para este año fiscal.')

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Planilla de Aguinaldo generada y contabilizada para {generados} empleados.'})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error in aguinaldo batch: {e}")
        return jsonify({'error': f'Error procesando aguinaldo: {str(e)}'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/nomina/<int:nomina_id>/contabilizar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def contabilizar_nomina_borrador(nomina_id):
    """Contabiliza una nómina existente que quedó en estado Borrador."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerNominaPorIDParaContabilizar',
            (nomina_id,),
            fallback_sql="""
            SELECT n.ID, n.EmpleadoID, e.NombreCompleto, e.Cargo, e.SalarioBase, e.UsuarioID,
                   n.PeriodoInicio, n.PeriodoFin, n.SalarioBruto, n.HorasExtras, n.MontoHorasExtras,
                   n.OtrosIngresos, n.TotalDevengado, n.INSSLaboral, n.IRMensual,
                   n.PensionAlimenticia, n.ValesDescontados, n.TotalDeducciones,
                   n.SalarioNeto, n.INSSPatronal, n.INATEC, n.Estado
            FROM Nomina n WITH (UPDLOCK, HOLDLOCK)
            JOIN Empleados e ON n.EmpleadoID = e.ID
            WHERE n.ID = ?
        """,
        )
        nom = cursor.fetchone()
        if not nom:
            return jsonify({'error': 'Nómina no encontrada.'}), 404
        if nom.Estado in ('Contabilizada', 'Pagada'):
            return jsonify({'error': 'Esta nómina ya está contabilizada.'}), 400

        from app.services.contabilidad_service import ContabilidadService
        es_aguinaldo = float(nom.SalarioBruto) == 0 and float(nom.OtrosIngresos) > 0
        _validar_no_periodo_futuro(nom.PeriodoInicio, nom.PeriodoFin, aguinaldo=es_aguinaldo)
        if es_aguinaldo:
            asiento = ContabilidadService.contabilizar_aguinaldo(
                cursor=cursor,
                usuario_id=current_user.id,
                nomina_id=nom.ID,
                empleado_nombre=nom.NombreCompleto,
                monto_aguinaldo=float(nom.TotalDevengado),
                cargo=nom.Cargo,
                ip=request.remote_addr,
                fecha=_fecha_contable_periodo(nom.PeriodoFin),
            )
        else:
            asiento = _contabilizar_nomina_segura(
                cursor=cursor,
                usuario_id=current_user.id,
                nomina_id=nom.ID,
                empleado_nombre=nom.NombreCompleto,
                salario_bruto=float(nom.TotalDevengado),
                inss_laboral=float(nom.INSSLaboral),
                ir_retenido=float(nom.IRMensual),
                inss_patronal=float(nom.INSSPatronal),
                inatec=float(nom.INATEC),
                pension_alimenticia=float(nom.PensionAlimenticia),
                vales_descontados=float(nom.ValesDescontados),
                salario_neto=float(nom.SalarioNeto),
                cargo=nom.Cargo,
                ip=request.remote_addr,
                fecha=_fecha_contable_periodo(nom.PeriodoFin),
            )
        execute_sp(
            cursor,
            'rrhh.sp_MarcarNominaContabilizada',
            (nom.ID,),
            fallback_sql="UPDATE Nomina SET Estado = 'Contabilizada' WHERE ID = ?",
        )
        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': f"Nómina #{nom.ID} contabilizada ({asiento['numero_comprobante']}).",
            'asiento_id': asiento['asiento_id'],
            'numero_comprobante': asiento['numero_comprobante'],
        })
    except ValueError as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error contabilizando nómina #{nomina_id}: {e}")
        return jsonify({'error': f'Error al contabilizar nómina: {str(e)}'}), 500
    finally:
        conn.close()


def _desembolsar_nomina_individual(cursor, nomina_id, metodo_pago, usuario_id, ip):
    """Ejecuta el desembolso verificable de una nómina Contabilizada dentro de la transacción activa."""
    from app.services.contabilidad_service import ContabilidadService, ContabilidadError

    metodo = str(metodo_pago or 'Efectivo').strip()
    cuentas_origen = {
        'Efectivo': ContabilidadService.CAJA_GENERAL_CS,
        'Transferencia': ContabilidadService.BANCOS_MN,
    }
    if metodo not in cuentas_origen:
        raise ValueError("Método de pago inválido. Use 'Efectivo' o 'Transferencia'.")
    cuenta_pago = cuentas_origen[metodo]

    execute_sp(
        cursor,
        'rrhh.sp_ObtenerNominaPorIDParaContabilizar',
        (int(nomina_id),),
        fallback_sql="""
        SELECT n.ID, n.EmpleadoID, e.NombreCompleto, e.Cargo, e.SalarioBase, e.UsuarioID,
               n.PeriodoInicio, n.PeriodoFin, n.SalarioBruto, n.HorasExtras, n.MontoHorasExtras,
               n.OtrosIngresos, n.TotalDevengado, n.INSSLaboral, n.IRMensual,
               n.PensionAlimenticia, n.ValesDescontados, n.TotalDeducciones,
               n.SalarioNeto, n.INSSPatronal, n.INATEC, n.Estado
        FROM Nomina n WITH (UPDLOCK, HOLDLOCK)
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE n.ID = ?
    """,
    )
    nom = cursor.fetchone()
    if not nom:
        raise LookupError('Nómina no encontrada.')
    if nom.Estado == 'Pagada':
        raise _NominaConflictError(
            f'La nómina #{nom.ID} ya se encuentra en estado Pagada. '
            'Operación idempotente rechazada para evitar doble desembolso.'
        )
    if nom.Estado != 'Contabilizada':
        raise ValueError(
            f'Solo se pueden desembolsar nóminas en estado Contabilizada (estado actual: {nom.Estado}).'
        )

    ref_pago = f'PAG-NOM-{nom.ID}'
    execute_sp(
        cursor,
        'rrhh.sp_VerificarAsientoPagoNominaExistente',
        (ref_pago,),
        fallback_sql="""
        SELECT TOP 1 ID, NumeroComprobante
        FROM AsientosDiario WITH (UPDLOCK, HOLDLOCK)
        WHERE ReferenciaExterna = ? AND Estado = 'Contabilizado'
        ORDER BY ID DESC
    """,
    )
    if cursor.fetchone():
        raise _NominaConflictError(
            f'Ya existe un comprobante de pago contabilizado ({ref_pago}) para esta nómina.'
        )

    monto_neto = amount(nom.SalarioNeto, 'Salario neto')
    asiento = None
    if monto_neto > Decimal('0.00'):
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerSaldoDisponibleCuentaBloqueo',
            (cuenta_pago,),
            fallback_sql="""
            SELECT ISNULL(SUM(d.Debe - d.Haber), 0) AS SaldoDisponible
            FROM CatalogoCuentas c WITH (UPDLOCK, HOLDLOCK)
            LEFT JOIN DetalleAsientos d WITH (UPDLOCK, HOLDLOCK) ON d.CuentaID = c.ID
            LEFT JOIN AsientosDiario a WITH (UPDLOCK, HOLDLOCK)
                ON a.ID = d.AsientoID AND a.Estado = 'Contabilizado'
            WHERE c.Codigo = ? AND c.Activa = 1
        """,
        )
        row_saldo = cursor.fetchone()
        raw_saldo = row_saldo[0] if row_saldo and row_saldo[0] is not None else 0
        saldo_disponible = Decimal(str(raw_saldo)).quantize(Decimal('0.01'))
        if saldo_disponible < monto_neto:
            raise ValueError(
                f'Fondos insuficientes en {metodo} ({cuenta_pago}): '
                f'disponible C${saldo_disponible:,.2f}, requerido C${monto_neto:,.2f}. '
                'El desembolso fue rechazado y la nómina se mantiene Contabilizada.'
            )

        fecha_pago = _fecha_contable_periodo(nom.PeriodoFin)
        try:
            asiento = ContabilidadService.crear_asiento(
                cursor=cursor,
                descripcion=f'Pago de nómina #{nom.ID} - {nom.NombreCompleto} ({metodo})',
                detalles=[
                    (
                        ContabilidadService.SUELDOS_POR_PAGAR,
                        monto_neto,
                        Decimal('0.00'),
                        f'Cancelación sueldos por pagar {nom.NombreCompleto}',
                    ),
                    (
                        cuenta_pago,
                        Decimal('0.00'),
                        monto_neto,
                        f'Desembolso nómina #{nom.ID} ({metodo})',
                    ),
                ],
                usuario_id=usuario_id,
                tipo_comprobante='EG',
                referencia_externa=ref_pago,
                tipo_documento='PagoNomina',
                ip=ip,
                fecha=fecha_pago,
            )
        except ContabilidadError as cerr:
            if 'cerrado' in str(cerr).lower():
                asiento = ContabilidadService.crear_asiento(
                    cursor=cursor,
                    descripcion=f'Pago de nómina #{nom.ID} - {nom.NombreCompleto} ({metodo})',
                    detalles=[
                        (
                            ContabilidadService.SUELDOS_POR_PAGAR,
                            monto_neto,
                            Decimal('0.00'),
                            f'Cancelación sueldos por pagar {nom.NombreCompleto}',
                        ),
                        (
                            cuenta_pago,
                            Decimal('0.00'),
                            monto_neto,
                            f'Desembolso nómina #{nom.ID} ({metodo})',
                        ),
                    ],
                    usuario_id=usuario_id,
                    tipo_comprobante='EG',
                    referencia_externa=ref_pago,
                    tipo_documento='PagoNomina',
                    ip=ip,
                    fecha=business_now(),
                )
            else:
                raise ValueError(str(cerr)) from cerr

    execute_sp(
        cursor,
        'rrhh.sp_MarcarNominaPagada',
        (int(nom.ID),),
        fallback_sql="UPDATE Nomina SET Estado = 'Pagada' WHERE ID = ? AND Estado = 'Contabilizada'",
    )

    detalle_audit = json.dumps(
        {
            'nomina_id': int(nom.ID),
            'empleado_id': int(nom.EmpleadoID),
            'empleado': nom.NombreCompleto,
            'salario_neto': float(monto_neto),
            'metodo_pago': metodo,
            'cuenta_origen': cuenta_pago,
            'referencia_pago': ref_pago,
            'asiento_id': asiento['asiento_id'] if asiento else None,
            'numero_comprobante': asiento['numero_comprobante'] if asiento else None,
        },
        ensure_ascii=False,
    )
    execute_sp(
        cursor,
        'seguridad.sp_RegistrarAuditoria',
        (
            usuario_id,
            'PAGO_NOMINA',
            'Nomina',
            int(nom.ID),
            json.dumps({'Estado': 'Contabilizada'}, ensure_ascii=False),
            detalle_audit,
            ip,
        ),
        fallback_sql="""
        INSERT INTO AuditLog (UsuarioID, Accion, Entidad, EntidadID, DatosAntes, DatosDespues, IP)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    )

    return {
        'nomina_id': int(nom.ID),
        'empleado': nom.NombreCompleto,
        'estado': 'Pagada',
        'metodo_pago': metodo,
        'cuenta_origen': cuenta_pago,
        'monto_pagado': float(monto_neto),
        'asiento_id': asiento['asiento_id'] if asiento else None,
        'numero_comprobante': asiento['numero_comprobante'] if asiento else None,
    }


@admin_bp.route('/rrhh/nomina/pagar/<int:nomina_id>', methods=['POST'])
@admin_bp.route('/api/rrhh/nomina/pagar/<int:nomina_id>', methods=['POST'])
@admin_bp.route('/api/rrhh/nomina/<int:nomina_id>/pagar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def pagar_nomina(nomina_id):
    """Desembolsa una nómina Contabilizada validando disponibilidad de Caja/Bancos e idempotencia."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        datos = request.form.to_dict() if request.form else {}
    metodo_pago = datos.get('metodo_pago', 'Efectivo')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        resultado = _desembolsar_nomina_individual(
            cursor=cursor,
            nomina_id=nomina_id,
            metodo_pago=metodo_pago,
            usuario_id=current_user.id,
            ip=request.remote_addr,
        )
        conn.commit()
        comp_txt = f" ({resultado['numero_comprobante']})" if resultado['numero_comprobante'] else ''
        msg = (
            f"Nómina #{resultado['nomina_id']} de {resultado['empleado']} pagada "
            f"por C${resultado['monto_pagado']:,.2f} vía {resultado['metodo_pago']}{comp_txt}."
        )
        return jsonify({
            'status': 'success',
            'mensaje': msg,
            **resultado,
        }), 200
    except LookupError as e:
        conn.rollback()
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 404
    except _NominaConflictError as e:
        conn.rollback()
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 409
    except ValueError as e:
        conn.rollback()
        try:
            flash(str(e), 'warning')
        except Exception:
            pass
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error desembolsando nómina #{nomina_id}: {e}")
        return jsonify({'status': 'error', 'error': f'Error interno al desembolsar nómina: {str(e)}'}), 500
    finally:
        conn.close()


@admin_bp.route('/rrhh/nomina/pagar-lote', methods=['POST'])
@admin_bp.route('/api/rrhh/nomina/pagar-lote', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def pagar_nomina_lote():
    """Desembolsa un lote de nóminas en estado Contabilizada de forma atómica."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        datos = request.form.to_dict() if request.form else {}
    metodo_pago = datos.get('metodo_pago', 'Efectivo')
    nomina_ids = datos.get('nomina_ids')
    periodo_inicio = datos.get('periodo_inicio')
    periodo_fin = datos.get('periodo_fin')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if not nomina_ids and periodo_inicio and periodo_fin:
            execute_sp(
                cursor,
                'rrhh.sp_ListarNominasContabilizadasPorPeriodoBloqueo',
                (as_date(periodo_inicio), as_date(periodo_fin)),
                fallback_sql=(
                    "SELECT ID FROM Nomina WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE PeriodoInicio >= ? AND PeriodoFin <= ? AND Estado = 'Contabilizada' "
                    "ORDER BY ID ASC"
                ),
            )
            nomina_ids = [int(r[0]) for r in cursor.fetchall()]

        if not nomina_ids or not isinstance(nomina_ids, (list, tuple)):
            raise ValueError('No se encontraron nóminas en estado Contabilizada para desembolsar.')

        pagadas = []
        for nid in nomina_ids:
            pagadas.append(
                _desembolsar_nomina_individual(
                    cursor=cursor,
                    nomina_id=int(nid),
                    metodo_pago=metodo_pago,
                    usuario_id=current_user.id,
                    ip=request.remote_addr,
                )
            )
        conn.commit()
        total_desembolsado = sum(item['monto_pagado'] for item in pagadas)
        return jsonify({
            'status': 'success',
            'mensaje': f"Se desembolsaron {len(pagadas)} nóminas por un total de C${total_desembolsado:,.2f}.",
            'pagadas': pagadas,
            'total_desembolsado': round(total_desembolsado, 2),
        }), 200
    except LookupError as e:
        conn.rollback()
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 404
    except _NominaConflictError as e:
        conn.rollback()
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 409
    except ValueError as e:
        conn.rollback()
        try:
            flash(str(e), 'warning')
        except Exception:
            pass
        return jsonify({'status': 'error', 'error': str(e), 'mensaje': str(e)}), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error desembolsando lote de nóminas: {e}")
        return jsonify({'status': 'error', 'error': f'Error interno al desembolsar lote: {str(e)}'}), 500
    finally:
        conn.close()

# ==============================================================================
# GESTIÓN DE VACACIONES, SALDOS Y RECOMENDACIÓN ROTATIVA SEMESTRAL
# ==============================================================================

@admin_bp.route('/api/rrhh/vacaciones/saldos', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def obtener_saldos_vacaciones():
    """Calcula el balance de vacaciones y semáforo de riesgo para todos los empleados activos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosCompletos',
            fallback_sql="""
                SELECT ID, NombreCompleto, Cargo, Cedula, FechaIngreso
                FROM Empleados WHERE EstadoEmpleado = 'Activo'
            """
        )
        empleados = cursor.fetchall()
        
        # Obtener vacaciones tomadas por empleado
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerTotalVacacionesGozadasPorEmpleado',
            fallback_sql="""
                SELECT EmpleadoID, ISNULL(SUM(DiasOtorgados), 0) AS TotalGozadas
                FROM LicenciasEmpleados
                WHERE TipoLicencia = 'Vacaciones'
                GROUP BY EmpleadoID
            """
        )
        gozadas_map = {row[0]: float(row[1]) for row in cursor.fetchall()}
        
        resultado = []
        hoy = business_now().date()
        for emp in empleados:
            dias_gozados = gozadas_map.get(emp.ID, 0.0)
            saldo = calcular_saldo_vacaciones_empleado(
                fecha_ingreso=emp.FechaIngreso,
                dias_gozados=dias_gozados,
                as_of=hoy
            )
            saldo['empleado_id'] = emp.ID
            saldo['nombre'] = emp.NombreCompleto
            saldo['cargo'] = emp.Cargo
            saldo['cedula'] = getattr(emp, 'Cedula', '')
            saldo['fecha_ingreso'] = as_date(emp.FechaIngreso).isoformat()
            resultado.append(saldo)
            
        return jsonify({'status': 'success', 'saldos': resultado})
    except Exception as e:
        current_app.logger.exception('Error al obtener saldos de vacaciones')
        return jsonify({'error': 'Error interno al consultar saldos de vacaciones.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/vacaciones/recomendar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def generar_recomendacion_vacaciones():
    """Genera y guarda el plan sugerido de vacaciones rotativas para evitar acumulación."""
    datos = request.get_json(silent=True) or {}
    meses_proyeccion = int(datos.get('meses', 6))
    guardar = bool(datos.get('guardar', True))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosCompletos',
            fallback_sql="SELECT ID, NombreCompleto, Cargo, FechaIngreso FROM Empleados WHERE EstadoEmpleado = 'Activo'"
        )
        empleados = cursor.fetchall()
        
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerTotalVacacionesGozadasPorEmpleado',
            fallback_sql="""
                SELECT EmpleadoID, ISNULL(SUM(DiasOtorgados), 0) AS TotalGozadas
                FROM LicenciasEmpleados
                WHERE TipoLicencia = 'Vacaciones'
                GROUP BY EmpleadoID
            """
        )
        gozadas_map = {row[0]: float(row[1]) for row in cursor.fetchall()}
        
        hoy = business_now().date()
        saldos_empleados = []
        for emp in empleados:
            dias_gozados = gozadas_map.get(emp.ID, 0.0)
            saldo = calcular_saldo_vacaciones_empleado(emp.FechaIngreso, dias_gozados, as_of=hoy)
            saldos_empleados.append({
                'empleado_id': emp.ID,
                'nombre': emp.NombreCompleto,
                'cargo': emp.Cargo,
                'dias_disponibles': saldo['dias_disponibles'],
                'alerta_semaforo': saldo['alerta_semaforo'],
            })
            
        inicio_plan = hoy + timedelta(days=7)
        propuestas = generar_plan_recomendado_vacaciones(
            empleados_saldos=saldos_empleados,
            fecha_inicio_plan=inicio_plan,
            meses_proyeccion=meses_proyeccion,
            max_por_cargo=1
        )
        
        guardadas = []
        if guardar:
            for p in propuestas:
                execute_sp(
                    cursor,
                    'rrhh.sp_GuardarPropuestaVacaciones',
                    (p['empleado_id'], p['fecha_inicio'], p['fecha_fin'], p['dias'], p['motivo']),
                    fallback_sql="""
                        INSERT INTO PropuestasVacaciones (EmpleadoID, FechaInicio, FechaFin, Dias, Motivo, Estado)
                        OUTPUT INSERTED.ID
                        VALUES (?, ?, ?, ?, ?, 'Propuesta')
                    """
                )
                row = cursor.fetchone() if cursor.description else None
                prop_id = row[0] if row else None
                p_copy = dict(p)
                p_copy['id'] = prop_id
                guardadas.append(p_copy)
            conn.commit()
        else:
            guardadas = propuestas
            
        return jsonify({'status': 'success', 'propuestas': guardadas})
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error al generar propuestas de vacaciones')
        return jsonify({'error': 'Error interno al generar propuesta de vacaciones.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/vacaciones/propuestas', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def listar_propuestas_vacaciones():
    """Lista propuestas de vacaciones registradas."""
    anio = request.args.get('anio', type=int)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarPropuestasVacaciones',
            (anio,),
            fallback_sql="""
                SELECT p.ID, p.EmpleadoID, e.NombreCompleto, e.Cargo, p.FechaInicio, p.FechaFin, p.Dias, p.Motivo, p.Estado, p.CreadoEn
                FROM PropuestasVacaciones p
                JOIN Empleados e ON p.EmpleadoID = e.ID
                WHERE (? IS NULL OR YEAR(p.FechaInicio) = ?)
                ORDER BY p.FechaInicio ASC
            """
        )
        rows = cursor.fetchall() or []
        res = []
        for r in rows:
            res.append({
                'id': r[0],
                'empleado_id': r[1],
                'nombre': r[2],
                'cargo': r[3],
                'fecha_inicio': as_date(r[4]).isoformat(),
                'fecha_fin': as_date(r[5]).isoformat(),
                'dias': r[6],
                'motivo': r[7],
                'estado': r[8],
            })
        return jsonify({'status': 'success', 'propuestas': res})
    except Exception as e:
        current_app.logger.exception('Error al listar propuestas de vacaciones')
        return jsonify({'error': 'Error al consultar propuestas.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/vacaciones/aprobar/<int:propuesta_id>', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def aprobar_propuesta_vacaciones(propuesta_id):
    """Aprueba una propuesta de vacaciones y genera la licencia formal."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_AprobarPropuestaVacaciones',
            (propuesta_id, current_user.id),
            fallback_sql="""
                DECLARE @EmpID INT, @Ini DATE, @Fin DATE, @Dias INT, @Motivo NVARCHAR(255);
                SELECT @EmpID = EmpleadoID, @Ini = FechaInicio, @Fin = FechaFin, @Dias = Dias, @Motivo = Motivo
                FROM PropuestasVacaciones WHERE ID = ?;
                UPDATE PropuestasVacaciones SET Estado = 'Aprobada', AprobadoPor = ?, AprobadoEn = CURRENT_TIMESTAMP WHERE ID = ?;
                INSERT INTO LicenciasEmpleados (EmpleadoID, TipoLicencia, FechaInicio, FechaFin, DiasOtorgados, PagoEmpleador, PagoINSS, Observaciones, AprobadoPor)
                VALUES (@EmpID, 'Vacaciones', @Ini, @Fin, @Dias, 100.00, 0.00, ISNULL(@Motivo, 'Plan de Vacaciones'), ?);
            """
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Propuesta de vacaciones aprobada y registrada en licencias.'})
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error al aprobar propuesta de vacaciones')
        return jsonify({'error': 'Error al aprobar propuesta de vacaciones.'}), 500
    finally:
        conn.close()


# ==============================================================================
# GESTIÓN DE PRÉSTAMOS Y COBROS POR PÉRDIDAS
# ==============================================================================

@admin_bp.route('/api/rrhh/prestamos', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def gestionar_prestamos():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'POST':
            datos = request.json or {}
            empleado_id = positive_int(datos.get('empleado_id'), 'Empleado')
            monto_total = float(amount(datos.get('monto_total'), 'Monto total'))
            cuota_mensual = float(amount(datos.get('cuota_mensual'), 'Cuota mensual'))
            motivo = required_text(datos.get('motivo', 'Préstamo a empleado'), 'Motivo', 200)
            fecha_inicio = as_date(datos.get('fecha_inicio', business_now().date())).isoformat()
            
            execute_sp(
                cursor,
                'rrhh.sp_InsertarPrestamoEmpleado',
                (empleado_id, monto_total, cuota_mensual, monto_total, motivo, fecha_inicio, current_user.id),
                fallback_sql="""
                    INSERT INTO PrestamosEmpleados (EmpleadoID, MontoTotal, CuotaMensual, SaldoPendiente, Motivo, FechaInicio, Estado, CreadoPor)
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?, ?, ?, ?, 'Activo', ?)
                """
            )
            prestamo_id = cursor.fetchone()[0]
            conn.commit()
            return jsonify({'status': 'success', 'mensaje': 'Préstamo registrado exitosamente.', 'id': prestamo_id})
        else:
            empleado_id = request.args.get('empleado_id', type=int)
            execute_sp(
                cursor,
                'rrhh.sp_ListarTodosPrestamosActivos',
                (empleado_id,),
                fallback_sql="""
                    SELECT p.ID, p.EmpleadoID, e.NombreCompleto, p.MontoTotal, p.CuotaMensual, p.SaldoPendiente, p.Motivo, p.FechaInicio, p.Estado
                    FROM PrestamosEmpleados p
                    JOIN Empleados e ON p.EmpleadoID = e.ID
                    WHERE (? IS NULL OR p.EmpleadoID = ?) AND p.Estado = 'Activo'
                """
            )
            rows = cursor.fetchall() or []
            prestamos = [{
                'id': r[0], 'empleado_id': r[1], 'nombre': r[2], 'monto_total': float(r[3]),
                'cuota_mensual': float(r[4]), 'saldo_pendiente': float(r[5]), 'motivo': r[6],
                'fecha_inicio': as_date(r[7]).isoformat(), 'estado': r[8]
            } for r in rows]
            return jsonify({'status': 'success', 'prestamos': prestamos})
    except ValueError as ve:
        conn.rollback()
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error al gestionar préstamos')
        return jsonify({'error': 'Error interno en préstamos.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/perdidas', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def gestionar_cobros_perdidas():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'POST':
            datos = request.json or {}
            empleado_id = positive_int(datos.get('empleado_id'), 'Empleado')
            descripcion = required_text(datos.get('descripcion'), 'Descripción', 250)
            monto_total = float(amount(datos.get('monto_total'), 'Monto total'))
            cuota_mensual = float(amount(datos.get('cuota_mensual', monto_total), 'Cuota mensual'))
            numero_documento = datos.get('numero_documento', '')
            fecha_incidente = as_date(datos.get('fecha_incidente', business_now().date())).isoformat()
            
            execute_sp(
                cursor,
                'rrhh.sp_InsertarCobroPerdidaEmpleado',
                (empleado_id, descripcion, monto_total, monto_total, cuota_mensual, numero_documento, fecha_incidente, current_user.id),
                fallback_sql="""
                    INSERT INTO CobrosPerdidasEmpleados (EmpleadoID, Descripcion, MontoTotal, SaldoPendiente, CuotaMensual, NumeroDocumento, FechaIncidente, Estado, CreadoPor)
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
                """
            )
            cobro_id = cursor.fetchone()[0]
            conn.commit()
            return jsonify({'status': 'success', 'mensaje': 'Cobro por pérdida registrado exitosamente.', 'id': cobro_id})
        else:
            empleado_id = request.args.get('empleado_id', type=int)
            execute_sp(
                cursor,
                'rrhh.sp_ListarTodosCobrosPerdidasPendientes',
                (empleado_id,),
                fallback_sql="""
                    SELECT c.ID, c.EmpleadoID, e.NombreCompleto, c.Descripcion, c.MontoTotal, c.SaldoPendiente, c.NumeroDocumento, c.FechaIncidente, c.Estado
                    FROM CobrosPerdidasEmpleados c
                    JOIN Empleados e ON c.EmpleadoID = e.ID
                    WHERE (? IS NULL OR c.EmpleadoID = ?) AND c.Estado = 'Pendiente'
                """
            )
            rows = cursor.fetchall() or []
            cobros = [{
                'id': r[0], 'empleado_id': r[1], 'nombre': r[2], 'descripcion': r[3], 'monto_total': float(r[4]),
                'saldo_pendiente': float(r[5]), 'cuota_mensual': float(r[6] or r[5]), 'numero_documento': r[7],
                'fecha_incidente': as_date(r[8]).isoformat(), 'estado': r[9]
            } for r in rows]
            return jsonify({'status': 'success', 'cobros_perdidas': cobros})
    except ValueError as ve:
        conn.rollback()
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error al gestionar cobros por pérdidas')
        return jsonify({'error': 'Error interno en cobros por pérdidas.'}), 500
    finally:
        conn.close()


@admin_bp.route('/rrhh/nomina/<int:nomina_id>/colilla')
@login_required
@roles_required('Admin', 'SuperAdmin')
def colilla_pago(nomina_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerColillaNominaPorID',
        (nomina_id,),
        fallback_sql="""
        SELECT n.*, e.NombreCompleto, e.Cargo, e.Cedula, e.NumeroINSS, e.FechaIngreso
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE n.ID = ?
    """,
    )
    nomina = cursor.fetchone()
    conn.close()
    
    if not nomina:
        flash('Nómina no encontrada', 'error')
        return redirect(url_for('admin.rrhh'))
        
    aguinaldo_detalles = None
    if float(nomina.SalarioBruto) == 0 and float(nomina.OtrosIngresos) > 0:
        fecha_ingreso = nomina.FechaIngreso
        if type(fecha_ingreso) is str:
            fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
        elif hasattr(fecha_ingreso, 'date'):
            fecha_ingreso = fecha_ingreso.date()
            
        periodo_fin = nomina.PeriodoFin
        if type(periodo_fin) is str:
            periodo_fin = datetime.strptime(periodo_fin, '%Y-%m-%d').date()
        elif hasattr(periodo_fin, 'date'):
            periodo_fin = periodo_fin.date()
            
        fecha_inicio_ciclo = date(periodo_fin.year - 1, 12, 1) if periodo_fin.month == 11 else date(periodo_fin.year, 12, 1)
        if periodo_fin.month == 11 and periodo_fin.day == 30:
            fecha_inicio_ciclo = date(periodo_fin.year - 1, 12, 1)
            
        inicio_aguinaldo_real = max(fecha_inicio_ciclo, fecha_ingreso)
        dias_aguinaldo = (periodo_fin - inicio_aguinaldo_real).days + 1
        
        aguinaldo_proporcional = float(nomina.OtrosIngresos)
        salario_max_6m = aguinaldo_proporcional / (dias_aguinaldo / 365.0) if dias_aguinaldo > 0 else 0
        
        aguinaldo_detalles = {
            'dias': dias_aguinaldo,
            'salario_max_6m': round(salario_max_6m, 2)
        }
        
    # Obtener detalles desglosados de DetalleNomina
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerDetallesNomina',
        (nomina_id,),
        fallback_sql="""
            SELECT ID, NominaID, Concepto, Tipo, Monto, Descripcion
            FROM DetalleNomina WHERE NominaID = ?
            ORDER BY CASE Tipo WHEN 'Ingreso' THEN 1 WHEN 'Deduccion' THEN 2 WHEN 'Patronal' THEN 3 ELSE 4 END, ID ASC
        """
    )
    detalles_rows = cursor.fetchall() or []
    conn.close()

    return render_template('admin/colilla_pago.html', nomina=nomina, datetime=datetime, aguinaldo_detalles=aguinaldo_detalles, detalles=detalles_rows)

@admin_bp.route('/rrhh/reportes/inss_patronal')
@login_required
@roles_required('Admin', 'SuperAdmin')
def reporte_inss_patronal():
    mes = request.args.get('mes', datetime.now().month)
    anio = request.args.get('anio', datetime.now().year)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    execute_sp(
        cursor,
        'rrhh.sp_ReporteINSSPatronalMesAnio',
        (int(mes), int(anio)),
        fallback_sql="""
        SELECT e.NombreCompleto, e.NumeroINSS, n.TotalDevengado, n.INSSLaboral, n.INSSPatronal, n.INATEC
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE MONTH(n.PeriodoInicio) = ? AND YEAR(n.PeriodoInicio) = ?
    """,
    )
    registros = cursor.fetchall()
    
    total_laboral = sum(r.INSSLaboral for r in registros)
    total_patronal = sum(r.INSSPatronal for r in registros)
    total_inatec = sum(r.INATEC for r in registros)
    total_general = total_laboral + total_patronal + total_inatec
    
    conn.close()
    
    return render_template('admin/reporte_inss.html', 
        registros=registros,
        total_laboral=total_laboral,
        total_patronal=total_patronal,
        total_inatec=total_inatec,
        total_general=total_general,
        mes=mes, anio=anio, datetime=datetime)

@admin_bp.route('/rrhh/reportes/aguinaldo')
@login_required
@roles_required('Admin', 'SuperAdmin')
def reporte_aguinaldo():
    anio = request.args.get('anio', datetime.now().year)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    execute_sp(
        cursor,
        'rrhh.sp_ReporteAguinaldoAnio',
        (int(anio),),
        fallback_sql="""
        SELECT e.NombreCompleto, e.Cedula, e.FechaIngreso, n.PeriodoFin, n.OtrosIngresos AS AguinaldoMonto
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE YEAR(n.PeriodoFin) = ? AND n.SalarioBruto = 0 AND n.OtrosIngresos > 0
        ORDER BY e.NombreCompleto
    """,
    )
    
    nominas_aguinaldo = cursor.fetchall()
    
    registros = []
    total_aguinaldo = 0
    
    for n in nominas_aguinaldo:
        fecha_ingreso = n.FechaIngreso
        if type(fecha_ingreso) is str:
            fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
        elif hasattr(fecha_ingreso, 'date'):
            fecha_ingreso = fecha_ingreso.date()
            
        periodo_fin = n.PeriodoFin
        if type(periodo_fin) is str:
            periodo_fin = datetime.strptime(periodo_fin, '%Y-%m-%d').date()
        elif hasattr(periodo_fin, 'date'):
            periodo_fin = periodo_fin.date()
            
        fecha_inicio_ciclo = date(periodo_fin.year - 1, 12, 1) if periodo_fin.month == 11 else date(periodo_fin.year, 12, 1)
        if periodo_fin.month == 11 and periodo_fin.day == 30:
            fecha_inicio_ciclo = date(periodo_fin.year - 1, 12, 1)
            
        inicio_aguinaldo_real = max(fecha_inicio_ciclo, fecha_ingreso)
        dias_aguinaldo = (periodo_fin - inicio_aguinaldo_real).days + 1
        
        aguinaldo_proporcional = float(n.AguinaldoMonto)
        salario_max_6m = aguinaldo_proporcional / (dias_aguinaldo / 365.0) if dias_aguinaldo > 0 else 0
        
        registros.append({
            'nombre': n.NombreCompleto,
            'cedula': n.Cedula,
            'fecha_ingreso': fecha_ingreso.strftime('%d/%m/%Y'),
            'dias': dias_aguinaldo,
            'salario_base': round(salario_max_6m, 2),
            'monto': round(aguinaldo_proporcional, 2)
        })
        total_aguinaldo += aguinaldo_proporcional
        
    conn.close()
    
    return render_template('admin/reporte_aguinaldo.html',
        registros=registros,
        total_aguinaldo=total_aguinaldo,
        anio=anio, datetime=datetime)

@admin_bp.route('/api/rrhh/alertas', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def obtener_alertas():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    execute_sp(
        cursor,
        'rrhh.sp_AlertasCumpleanosProximos',
        fallback_sql="""
        SELECT NombreCompleto, FechaNacimiento
        FROM Empleados
        WHERE EstadoEmpleado = 'Activo' AND FechaNacimiento IS NOT NULL
          AND DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()), FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE())
           OR DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()) + 1, FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE())
    """,
    )
    cumples = [{'nombre': r.NombreCompleto, 'fecha': r.FechaNacimiento.strftime('%d/%m')} for r in cursor.fetchall()]
    
    execute_sp(
        cursor,
        'rrhh.sp_AlertasContratosPorVencer',
        fallback_sql="""
        SELECT NombreCompleto, FechaFinContrato, TipoContrato
        FROM Empleados
        WHERE EstadoEmpleado = 'Activo' 
          AND TipoContrato = 'Determinado'
          AND FechaFinContrato IS NOT NULL
          AND FechaFinContrato BETWEEN GETDATE() AND DATEADD(day, 30, GETDATE())
    """,
    )
    contratos = [{'nombre': r.NombreCompleto, 'fecha': r.FechaFinContrato.strftime('%d/%m/%Y')} for r in cursor.fetchall()]
    
    conn.close()
    return jsonify({'cumpleanos': cumples, 'contratos': contratos})

@admin_bp.route('/api/rrhh/empleados/referencias', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def get_empleados_referencias():
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_sp(
        cursor,
        'rrhh.sp_ObtenerEmpleadosReferenciasFoto',
        fallback_sql="SELECT ID, NombreCompleto, FotoPerfil FROM Empleados WHERE EstadoEmpleado = 'Activo' AND FotoPerfil IS NOT NULL",
    )
    empleados = [{'id': r.ID, 'nombre': r.NombreCompleto, 'foto': r.FotoPerfil} for r in cursor.fetchall()]
    conn.close()
    return jsonify(empleados)


@admin_bp.route('/api/rrhh/kiosco/marcar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def kiosco_marcar():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify(error='Datos inválidos'), 400
    cedula = datos.get('cedula')
    empleado_id = datos.get('empleado_id')
    tipo = datos.get('tipo')
    ahora = business_now()
    fecha = ahora.date().isoformat()
    hora = ahora.strftime('%H:%M:%S')
    
    if (not cedula and not empleado_id) or tipo not in ('entrada', 'salida'):
        return jsonify({'error': 'Faltan datos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if empleado_id:
            execute_sp(
                cursor,
                'rrhh.sp_ObtenerEmpleadoKioscoPorIDBloqueo',
                (empleado_id,),
                fallback_sql="SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM Empleados WITH (UPDLOCK, HOLDLOCK) WHERE ID = ? AND EstadoEmpleado = 'Activo'",
            )
        else:
            execute_sp(
                cursor,
                'rrhh.sp_ObtenerEmpleadoKioscoPorCedulaBloqueo',
                (cedula,),
                fallback_sql="SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM Empleados WITH (UPDLOCK, HOLDLOCK) WHERE Cedula = ? AND EstadoEmpleado = 'Activo'",
            )
            
        empleado = cursor.fetchone()
        if not empleado:
            return jsonify({'error': 'Cédula no encontrada o empleado inactivo'}), 404
            
        empleado_id = empleado.ID
        nombre = empleado.NombreCompleto
        
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerTurnoLaboralActivoDefecto',
            fallback_sql="SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos FROM TurnosLaborales WHERE Activo = 1 ORDER BY ID ASC",
        )
        turno = cursor.fetchone()
        clasificacion = resolver_horario_y_clasificar_asistencia(empleado, turno, ahora)
        turno_id = clasificacion['turno_id']
        
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo',
            (empleado_id, fecha),
            fallback_sql="SELECT ID, HoraEntrada, HoraSalida FROM Asistencia WITH (UPDLOCK, HOLDLOCK) WHERE EmpleadoID = ? AND Fecha = ?",
        )
        asistencia = cursor.fetchone()
        
        if tipo == 'entrada':
            if asistencia and asistencia.HoraEntrada:
                return jsonify(status='success', tipo='entrada', repetido=True,
                               mensaje=f'Hola {nombre}, ya tienes entrada registrada hoy.')
                
            estado_entrada = clasificacion['estado']
            
            if not asistencia:
                execute_sp(
                    cursor,
                    'rrhh.sp_InsertarEntradaAsistenciaConUsuario',
                    (empleado_id, turno_id, fecha, hora, estado_entrada, current_user.id),
                    fallback_sql="""
                    INSERT INTO Asistencia (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                )
            else:
                execute_sp(
                    cursor,
                    'rrhh.sp_ActualizarEntradaAsistenciaConUsuario',
                    (hora, estado_entrada, turno_id, current_user.id, asistencia.ID),
                    fallback_sql="""
                    UPDATE Asistencia SET HoraEntrada = ?, EstadoEntrada = ?, TurnoID = ?, RegistradoPor = ?
                    WHERE ID = ?
                """,
                )
                
            msg = f"¡Bienvenido {nombre}! Entrada registrada."
            
        elif tipo == 'salida':
            if not asistencia or not asistencia.HoraEntrada:
                return jsonify({'error': 'No puedes registrar salida sin haber marcado entrada.'}), 400
            if asistencia.HoraSalida:
                return jsonify(status='success', tipo='salida', repetido=True,
                               mensaje=f'Adiós {nombre}, ya tenías tu salida registrada hoy.')
            if not can_mark_exit(asistencia.HoraEntrada, ahora):
                return jsonify(error='Espera al menos un minuto desde la entrada para marcar salida.'), 409
                
            execute_sp(
                cursor,
                'rrhh.sp_ActualizarSalidaAsistenciaPorID',
                (hora, asistencia.ID),
                fallback_sql="UPDATE Asistencia SET HoraSalida = ? WHERE ID = ?",
            )
            msg = f"¡Adiós {nombre}! Salida registrada."
            
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': msg})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal error in kiosco: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()

@admin_bp.route('/rrhh/asistencia')
@login_required
@roles_required('Admin', 'SuperAdmin')
def rrhh_asistencia():
    fecha_str = request.args.get('fecha', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosBasico',
            fallback_sql="SELECT ID, NombreCompleto, Cargo FROM Empleados WHERE EstadoEmpleado = 'Activo'",
        )
        empleados = cursor.fetchall()
        total_esperados = len(empleados)
        
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaConTurnoPorFecha',
            (fecha_str,),
            fallback_sql="""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, t.Nombre AS Turno
            FROM Asistencia a
            LEFT JOIN TurnosLaborales t ON a.TurnoID = t.ID
            WHERE a.Fecha = ?
        """,
        )
        
        asistencia_raw = cursor.fetchall()
        asistencia_map = {row.EmpleadoID: row for row in asistencia_raw}
        
        presentes = 0
        a_tiempo = 0
        tardes = 0
        
        detalle = []
        for emp in empleados:
            registro = asistencia_map.get(emp.ID)
            estado = 'Ausente'
            entrada = '--:--'
            salida = '--:--'
            turno = 'General'
            
            if registro:
                presentes += 1
                estado = registro.EstadoEntrada or 'A Tiempo'
                try:
                    entrada = registro.HoraEntrada.strftime('%H:%M:%S') if registro.HoraEntrada else '--:--'
                except Exception:
                    entrada = str(registro.HoraEntrada)
                try:
                    salida = registro.HoraSalida.strftime('%H:%M:%S') if registro.HoraSalida else '--:--'
                except Exception:
                    salida = str(registro.HoraSalida) if registro.HoraSalida else '--:--'
                    
                turno = registro.Turno or 'General'
                
                if estado == 'A Tiempo':
                    a_tiempo += 1
                elif estado == 'Llegada Tardia':
                    tardes += 1
                    
            detalle.append({
                'nombre': emp.NombreCompleto,
                'cargo': emp.Cargo,
                'turno': turno,
                'entrada': entrada,
                'salida': salida,
                'estado': estado
            })
            
        ausentes = total_esperados - presentes
        
        def sort_key(x):
            order = {'Ausente': 0, 'Llegada Tardia': 1, 'A Tiempo': 2}
            return (order.get(x['estado'], 99), x['nombre'])
            
        detalle.sort(key=sort_key)
        
        stats = {
            'esperados': total_esperados,
            'presentes': presentes,
            'a_tiempo': a_tiempo,
            'tardes': tardes,
            'ausentes': ausentes
        }
        
        return render_template('admin/asistencia.html', 
                               fecha=fecha_str, 
                               stats=stats, 
                               detalle=detalle)
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/asistencia_detalle_json')
@login_required
@roles_required('Admin', 'SuperAdmin')
def rrhh_asistencia_detalle_json():
    fecha_str = request.args.get('fecha', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'rrhh.sp_ListarEmpleadosActivosBasico',
            fallback_sql="SELECT ID, NombreCompleto, Cargo FROM Empleados WHERE EstadoEmpleado = 'Activo'",
        )
        empleados = cursor.fetchall()
        total_esperados = len(empleados)
        
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaConTurnoPorFecha',
            (fecha_str,),
            fallback_sql="""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, t.Nombre AS Turno
            FROM Asistencia a
            LEFT JOIN TurnosLaborales t ON a.TurnoID = t.ID
            WHERE a.Fecha = ?
        """,
        )
        
        asistencia_raw = cursor.fetchall()
        asistencia_map = {row.EmpleadoID: row for row in asistencia_raw}
        
        presentes = 0
        a_tiempo = 0
        tardes = 0
        
        detalle = []
        for emp in empleados:
            registro = asistencia_map.get(emp.ID)
            estado = 'Ausente'
            entrada = '--:--'
            salida = '--:--'
            turno = 'General'
            
            if registro:
                presentes += 1
                estado = registro.EstadoEntrada or 'A Tiempo'
                try:
                    entrada = registro.HoraEntrada.strftime('%H:%M:%S') if registro.HoraEntrada else '--:--'
                except Exception:
                    entrada = str(registro.HoraEntrada)
                try:
                    salida = registro.HoraSalida.strftime('%H:%M:%S') if registro.HoraSalida else '--:--'
                except Exception:
                    salida = str(registro.HoraSalida) if registro.HoraSalida else '--:--'
                turno = registro.Turno or 'General'
                if estado == 'A Tiempo':
                    a_tiempo += 1
                elif estado == 'Llegada Tardia':
                    tardes += 1
                    
            detalle.append({
                'nombre': emp.NombreCompleto,
                'cargo': emp.Cargo,
                'turno': turno,
                'entrada': entrada,
                'salida': salida,
                'estado': estado
            })
            
        ausentes = total_esperados - presentes
        
        def sort_key(x):
            order = {'Ausente': 0, 'Llegada Tardia': 1, 'A Tiempo': 2}
            return (order.get(x['estado'], 99), x['nombre'])
            
        detalle.sort(key=sort_key)
        
        stats = {
            'esperados': total_esperados,
            'presentes': presentes,
            'a_tiempo': a_tiempo,
            'tardes': tardes,
            'ausentes': ausentes
        }
        return jsonify({'status': 'success', 'stats': stats, 'detalle': detalle})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
