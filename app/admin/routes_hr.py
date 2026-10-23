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
from app.services.validation import amount, positive_int, required_text
from app.services.hr_calculations import as_date, absent_dates, liquidation, can_mark_exit
from app.services.business_time import business_now

def _fecha_contable_periodo(periodo_fin):
    """Retorna la fecha contable dentro del mes del período sin quedar en el futuro si es el mes en curso."""
    fin = date.fromisoformat(str(periodo_fin))
    ahora = business_now()
    if (fin.year, fin.month) == (ahora.year, ahora.month) and ahora.date() < fin:
        return ahora
    return datetime(fin.year, fin.month, fin.day, 17, 0, 0)


def validar_periodo_nomina(cursor, empleado_id, inicio, fin, aguinaldo=False):
    inicio = date.fromisoformat(str(inicio)); fin = date.fromisoformat(str(fin))
    if not aguinaldo:
        import calendar
        if inicio.day != 1 or fin != date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1]):
            raise ValueError('El cálculo mensual requiere el primer y último día del mismo mes.')
    if fin < inicio:
        raise ValueError('El período final no puede ser anterior al inicial.')
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
            fallback_sql='SELECT Cargo,PerfilPuesto,Obligaciones,RequisitosCompetencias,ActualizadoEn FROM rrhh.PerfilesPuesto ORDER BY Cargo',
        )
        perfiles = [{
            'cargo': row.Cargo, 'perfil': row.PerfilPuesto,
            'obligaciones': row.Obligaciones, 'competencias': row.RequisitosCompetencias,
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
                datos.get('nombre'), datos.get('cedula'),
                datos.get('fecha_nacimiento') or None, datos.get('genero') or None,
                datos.get('direccion') or None, datos.get('telefono') or None,
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

def obtener_dias_ausentes_auto(cursor, empleado_id, periodo_inicio, periodo_fin):
    inicio, fin = as_date(periodo_inicio), as_date(periodo_fin)
    if fin < inicio:
        raise ValueError('El período final no puede ser anterior al inicial.')
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
    return len(absent_dates(inicio, fin, asistidas, cursor.fetchall()))


@admin_bp.route('/api/rrhh/nomina/calcular', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_nomina():
    datos = request.json
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
        salario_base_efectivo = salario_base - monto_ausencias

        total_devengado = salario_base_efectivo + monto_horas_extras + monto_feriados + otros_ingresos

        inss_laboral = total_devengado * (tasa_inss_laboral / 100)

        renta_neta_mensual = total_devengado - inss_laboral
        renta_neta_anual = renta_neta_mensual * 12

        ir_anual = 0
        tabla_ir = json.loads(config.get('ir_tabla', '[]'))
        for estrato in tabla_ir:
            if renta_neta_anual >= estrato['desde'] and renta_neta_anual <= estrato['hasta']:
                ir_anual = ((renta_neta_anual - estrato['exceso']) * estrato['tasa'] / 100) + estrato['base']
                break

        ir_mensual = ir_anual / 12

        vales_descontados = 0
        if emp.UsuarioID:
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerSumaValesPendientesUsuario',
                (emp.UsuarioID,),
                fallback_sql="SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE EmpleadoID = ? AND Descontado = 0",
            )
            vales_pendientes = float(cursor.fetchone()[0])
            vales_descontados = vales_pendientes

        salario_neto_pre = total_devengado - inss_laboral - ir_mensual
        pension_alimenticia = calcular_deducciones_judiciales(
            cursor, int(empleado_id), salario_neto_pre, periodo_fin
        )

        total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
        salario_neto = total_devengado - total_deducciones

        inss_patronal = total_devengado * (tasa_inss_patronal / 100)
        inatec = total_devengado * (tasa_inatec / 100)

        salario_base_efectivo = float(amount(salario_base_efectivo, 'Salario efectivo'))
        monto_horas_extras = float(amount(monto_horas_extras))
        otros_ingresos = float(amount(otros_ingresos))
        monto_feriados = float(amount(monto_feriados))
        total_devengado = amount(salario_base_efectivo) + amount(monto_horas_extras) + amount(otros_ingresos) + amount(monto_feriados)
        inss_laboral = amount(inss_laboral); ir_mensual = amount(ir_mensual)
        pension_alimenticia = amount(pension_alimenticia); vales_descontados = amount(vales_descontados)
        total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
        salario_neto = amount(total_devengado - total_deducciones, 'Salario neto')
        inss_patronal = amount(inss_patronal); inatec = amount(inatec)
        if total_devengado <= 0:
            raise ValueError('Revise las ausencias: no hay salario devengado para contabilizar.')

        execute_sp(
            cursor,
            'rrhh.sp_InsertarNominaMensual',
            (
                int(empleado_id), periodo_inicio, periodo_fin, salario_base_efectivo,
                horas_extras, monto_horas_extras, (otros_ingresos + monto_feriados), total_devengado,
                inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
                total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
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

        if vales_descontados > 0 and emp.UsuarioID:
            execute_sp(
                cursor,
                'contabilidad.sp_MarcarValesDescontadosUsuario',
                (emp.UsuarioID,),
                fallback_sql="UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0",
            )

        from app.services.contabilidad_service import ContabilidadService
        ContabilidadService.contabilizar_nomina(
            cursor=cursor,
            usuario_id=current_user.id,
            nomina_id=nomina_id,
            empleado_nombre=emp.NombreCompleto,
            salario_bruto=total_devengado,
            inss_laboral=inss_laboral,
            ir_retenido=ir_mensual,
            inss_patronal=inss_patronal,
            inatec=inatec,
            pension_alimenticia=pension_alimenticia,
            vales_descontados=vales_descontados,
            salario_neto=salario_neto,
            cargo=emp.Cargo,
            ip=request.remote_addr,
            fecha=_fecha_contable_periodo(periodo_fin)
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
                'total_devengado': round(total_devengado, 2),
                'inss_laboral': round(inss_laboral, 2),
                'tasa_inss_laboral': tasa_inss_laboral,
                'ir_mensual': round(ir_mensual, 2),
                'renta_neta_anual_proyectada': round(renta_neta_anual, 2),
                'pension_alimenticia': round(pension_alimenticia, 2),
                'vales_descontados': round(vales_descontados, 2),
                'total_deducciones': round(total_deducciones, 2),
                'salario_neto': round(salario_neto, 2),
                'inss_patronal': round(inss_patronal, 2),
                'tasa_inss_patronal': tasa_inss_patronal,
                'inatec': round(inatec, 2),
                'total_empleados': total_empleados
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
    datos = request.json
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
            salario_base_efectivo = max(0, salario_base - monto_ausencias)
            
            total_devengado = salario_base_efectivo
            
            inss_laboral = total_devengado * (tasa_inss_laboral / 100)
            
            renta_neta_anual = (total_devengado - inss_laboral) * 12
            ir_anual = 0
            for estrato in tabla_ir:
                if renta_neta_anual >= estrato['desde'] and renta_neta_anual <= estrato['hasta']:
                    ir_anual = ((renta_neta_anual - estrato['exceso']) * estrato['tasa'] / 100) + estrato['base']
                    break
            ir_mensual = ir_anual / 12
            
            vales_descontados = 0
            if emp.UsuarioID:
                execute_sp(
                    cursor,
                    'contabilidad.sp_ObtenerSumaValesPendientesUsuario',
                    (emp.UsuarioID,),
                    fallback_sql="SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE EmpleadoID = ? AND Descontado = 0",
                )
                vales_descontados = float(cursor.fetchone()[0])
            
            salario_neto_pre = total_devengado - inss_laboral - ir_mensual
            pension_alimenticia = calcular_deducciones_judiciales(
                cursor, emp.ID, salario_neto_pre, periodo_fin
            )
            
            total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
            salario_neto = total_devengado - total_deducciones
            
            inss_patronal = total_devengado * (tasa_inss_patronal / 100)
            inatec = total_devengado * (tasa_inatec / 100)
            
            salario_base_efectivo = amount(salario_base_efectivo)
            total_devengado = salario_base_efectivo
            inss_laboral = amount(inss_laboral); ir_mensual = amount(ir_mensual)
            pension_alimenticia = amount(pension_alimenticia); vales_descontados = amount(vales_descontados)
            total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
            salario_neto = amount(total_devengado - total_deducciones, 'Salario neto')
            inss_patronal = amount(inss_patronal); inatec = amount(inatec)
            if total_devengado <= 0:
                raise ValueError(f'Revise las ausencias de {emp.NombreCompleto}: no hay salario devengado.')

            execute_sp(
                cursor,
                'rrhh.sp_InsertarNominaBatch',
                (
                    emp.ID, periodo_inicio, periodo_fin, salario_base_efectivo, total_devengado,
                    inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
                    total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
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
            from app.services.contabilidad_service import ContabilidadService
            ContabilidadService.contabilizar_nomina(cursor, current_user.id, nomina_id,
                emp.NombreCompleto, total_devengado, inss_laboral, ir_mensual,
                inss_patronal, inatec, pension_alimenticia, vales_descontados,
                salario_neto, emp.Cargo, request.remote_addr, fecha=_fecha_contable_periodo(periodo_fin))
            
            if vales_descontados > 0 and emp.UsuarioID:
                execute_sp(
                    cursor,
                    'contabilidad.sp_MarcarValesDescontadosUsuario',
                    (emp.UsuarioID,),
                    fallback_sql="UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0",
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
        logging.error(f"Internal server error in batch payroll: {e}")
        return jsonify({'error': 'Error procesando la planilla batch. Rollback ejecutado.'}), 500
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
            asiento = ContabilidadService.contabilizar_nomina(
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
        
    return render_template('admin/colilla_pago.html', nomina=nomina, datetime=datetime, aguinaldo_detalles=aguinaldo_detalles)

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
            fallback_sql="SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos FROM TurnosLaborales WHERE Activo = 1",
        )
        turno = cursor.fetchone()
        turno_id = turno.ID if turno else 1
        
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
                
            estado_entrada = 'A Tiempo'
            from datetime import datetime as dt, timedelta
            
            if empleado.HoraEntrada:
                hora_limite = (dt.combine(ahora.date(), empleado.HoraEntrada) + timedelta(minutes=15)).time()
            elif turno:
                hora_limite = (dt.combine(ahora.date(), turno.HoraEntrada) + timedelta(minutes=turno.ToleranciaMinutos or 0)).time()
            else:
                hora_limite = None

            if hora_limite:
                hora_actual = ahora.time()
                if hora_actual > hora_limite:
                    estado_entrada = 'Llegada Tardia'
            
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
