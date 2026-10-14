# app/admin/routes_hr.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback
import base64
import os
import uuid
from flask import current_app

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime, date, timedelta
from app.services.validation import amount, required_text

def validar_periodo_nomina(cursor, empleado_id, inicio, fin, aguinaldo=False):
    inicio=date.fromisoformat(str(inicio)); fin=date.fromisoformat(str(fin))
    if not aguinaldo:
        import calendar
        if inicio.day != 1 or fin != date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1]):
            raise ValueError('El cálculo mensual requiere el primer y último día del mismo mes.')
    if fin<inicio:
        raise ValueError('El período final no puede ser anterior al inicial.')
    cursor.execute('SELECT ID FROM Empleados WITH(UPDLOCK,HOLDLOCK) WHERE ID=?',empleado_id)
    if not cursor.fetchone():
        raise ValueError('Empleado inexistente.')
    # Aguinaldo se guarda actualmente como nómina sin salario base.
    comparison='=' if aguinaldo else '>'
    cursor.execute(f"SELECT ID FROM Nomina WHERE EmpleadoID=? AND PeriodoInicio<=? AND PeriodoFin>=? AND SalarioBruto {comparison} 0",empleado_id,fin,inicio)
    if cursor.fetchone():
        raise ValueError('Ya existe una nómina para este empleado y período. Revise el registro anterior.')


def calcular_deducciones_judiciales(cursor, empleado_id, salario_neto_pre, fecha):
    """Calcula obligaciones vigentes por porcentaje y monto fijo."""
    cursor.execute(
        "SELECT PorcentajeSalarioNeto, MontoFijo FROM DeduccionesJudiciales "
        "WHERE EmpleadoID=? AND Activa=1 AND FechaInicio<=? "
        "AND (FechaFin IS NULL OR FechaFin>=?)",
        empleado_id, fecha, fecha
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

    # Empleados activos
    cursor.execute("""
        SELECT e.*, u.Username 
        FROM Empleados e 
        LEFT JOIN Usuarios u ON e.UsuarioID = u.ID
        ORDER BY e.NombreCompleto
    """)
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
            'hora_salida': r.HoraSalida.strftime('%H:%M') if r.HoraSalida else ''
        })

    # Nóminas recientes
    cursor.execute("""
        SELECT TOP 20 n.ID, e.NombreCompleto, n.PeriodoInicio, n.PeriodoFin,
               n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto, n.Estado,
               n.SalarioBruto, n.OtrosIngresos
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        ORDER BY n.FechaGeneracion DESC
    """)
    nominas = [{
        'id': r.ID, 'empleado': r.NombreCompleto,
        'periodo': f"{r.PeriodoInicio.strftime('%d/%m')} - {r.PeriodoFin.strftime('%d/%m/%Y')}",
        'devengado': float(r.TotalDevengado), 'deducciones': float(r.TotalDeducciones),
        'neto': float(r.SalarioNeto), 'estado': r.Estado,
        'es_aguinaldo': float(r.SalarioBruto) == 0 and float(r.OtrosIngresos) > 0
    } for r in cursor.fetchall()]

    # Configuraciones de tasas
    cursor.execute("SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')")
    tasas = {r.Clave: r.Valor for r in cursor.fetchall()}

    # Conteo de empleados activos (para determinar tasa patronal)
    cursor.execute("SELECT COUNT(*) FROM Empleados WHERE EstadoEmpleado = 'Activo'")
    total_activos = cursor.fetchone()[0]

    # Asistencia de hoy (Monitor)
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, e.NombreCompleto, e.Cargo
        FROM Asistencia a 
        JOIN Empleados e ON a.EmpleadoID = e.ID
        WHERE a.Fecha = ?
        ORDER BY a.HoraEntrada DESC
    """, fecha_hoy)
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
        monitor_hoy=monitor_hoy, datetime=datetime)


@admin_bp.route('/api/rrhh/asistencia_hoy_json', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def rrhh_asistencia_hoy_json():
    """Endpoint para polling automático del monitor de asistencia."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, e.NombreCompleto, e.Cargo
            FROM Asistencia a 
            JOIN Empleados e ON a.EmpleadoID = e.ID
            WHERE a.Fecha = ?
            ORDER BY a.HoraEntrada DESC
        """, fecha_hoy)
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
    datos = request.json
    campos_requeridos = ['nombre', 'cedula', 'cargo', 'fecha_ingreso', 'salario_base']
    if not all(datos.get(c) for c in campos_requeridos):
        return jsonify({'error': 'Faltan campos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        foto_path = None
        descriptor_str = None
        if 'foto' in datos and datos['foto']:
            # Extraer descriptor con la IA nativa (SFace)
            from app.services.face_service import face_service
            import json
            resultado_ia = face_service.procesar_imagen_registro_base64(datos['foto'])
            if resultado_ia['status'] == 'success':
                descriptor_str = json.dumps(resultado_ia['descriptor'])
            else:
                # Opcional: Podrías retornar error aquí si el rostro es obligatorio.
                # Como el sistema tiene fallback, lo dejamos pasar como NULL si falla pero avisamos en el log.
                import logging
                logging.warning(f"No se pudo extraer descriptor SFace: {resultado_ia['message']}")

            # Guardar imagen en disco
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

        cursor.execute("""
            INSERT INTO Empleados (NombreCompleto, Cedula, FechaNacimiento, Genero, Direccion,
                Telefono, CorreoElectronico, NumeroINSS, Cargo, FechaIngreso, TipoContrato, FechaFinContrato,
                TipoJornada, SalarioBase, FormaPago, ConsentimientoDatos, FechaConsentimiento, FotoPerfil, HoraEntrada, HoraSalida, FaceDescriptor)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, ?, ?)
        """,
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
        )
        
        row = cursor.fetchone()
        nuevo_id = row.ID if row else None
        conn.commit()

        # Actualizar la caché de reconocimiento facial en caliente
        if nuevo_id and descriptor_str:
            import json
            face_service.actualizar_cache_empleado(nuevo_id, json.loads(descriptor_str))
            
        return jsonify({'status': 'success', 'mensaje': 'Empleado registrado'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
        cursor.execute("UPDATE Empleados SET EstadoEmpleado='Suspendido' WHERE ID=?", id)
        if cursor.rowcount == 0:
            return jsonify({'error': 'Empleado no encontrado'}), 404
            
        conn.commit()
        # Eliminar también de la caché de rostros si existe
        from app.services.face_service import face_service
        if id in face_service.encodings_cache:
            del face_service.encodings_cache[id]
            
        return jsonify({'status': 'success', 'mensaje': 'Empleado suspendido. Se conserva todo el historial laboral y contable.'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error eliminando empleado: {e}")
        # Error 547 es de Foreign Key Constraint en SQL Server
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
        cursor.execute("UPDATE Empleados SET HoraEntrada = ?, HoraSalida = ? WHERE ID = ?", hora_entrada, hora_salida, id)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Horario actualizado'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
            cursor.execute(
                "SELECT d.ID, d.EmpleadoID, e.NombreCompleto, d.TipoDeduccion, d.Beneficiario, "
                "d.PorcentajeSalarioNeto, d.MontoFijo, d.NumeroJuzgado, d.FechaInicio, d.FechaFin, d.Activa "
                "FROM DeduccionesJudiciales d JOIN Empleados e ON e.ID=d.EmpleadoID ORDER BY d.Activa DESC, d.ID DESC"
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
        cursor.execute("SELECT ID FROM Empleados WHERE ID=?", empleado_id)
        if not cursor.fetchone():
            return jsonify(error='Empleado inexistente.'), 400
        cursor.execute(
            "INSERT INTO DeduccionesJudiciales (EmpleadoID,TipoDeduccion,Beneficiario,PorcentajeSalarioNeto,MontoFijo,NumeroJuzgado,FechaInicio,FechaFin) "
            "VALUES (?,?,?,?,?,?,?,?)",
            empleado_id, tipo, beneficiario, porcentaje, monto_fijo or None,
            (data.get('juzgado') or '').strip()[:50] or None, fecha_inicio, data.get('fecha_fin') or None
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
            cursor.execute(
                "SELECT i.ID, i.EmpleadoID, e.NombreCompleto, i.TipoIncidente, i.Gravedad, i.Descripcion, "
                "i.FechaIncidente, i.NotificadoMITRAB, i.AccionesCorrectivas "
                "FROM IncidentesLaborales i JOIN Empleados e ON e.ID=i.EmpleadoID ORDER BY i.FechaIncidente DESC"
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
        cursor.execute("SELECT ID FROM Empleados WHERE ID=?", empleado_id)
        if not cursor.fetchone():
            return jsonify(error='Empleado inexistente.'), 400
        notificado = bool(data.get('notificado_mitrab'))
        cursor.execute(
            "INSERT INTO IncidentesLaborales (EmpleadoID,TipoIncidente,Gravedad,Descripcion,FechaIncidente,NotificadoMITRAB,FechaNotificacionMITRAB,AccionesCorrectivas,RegistradoPor) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            empleado_id, tipo, gravedad, descripcion, fecha, notificado,
            datetime.now() if notificado else None,
            (data.get('acciones_correctivas') or '').strip()[:4000] or None, current_user.id
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
    if isinstance(periodo_inicio, str):
        periodo_inicio = datetime.strptime(periodo_inicio, '%Y-%m-%d').date()
    if isinstance(periodo_fin, str):
        periodo_fin = datetime.strptime(periodo_fin, '%Y-%m-%d').date()
        
    dias_totales = (periodo_fin - periodo_inicio).days + 1
    
    # 1. Contar domingos en el período (Días de descanso remunerados, no se marcan)
    domingos = sum(1 for i in range(dias_totales) if (periodo_inicio + timedelta(days=i)).weekday() == 6)
    dias_laborables_esperados = dias_totales - domingos
    if dias_laborables_esperados <= 0:
        return 0
        
    # Salvaguarda: Verificar si hay uso del módulo de asistencia en la empresa
    cursor.execute("SELECT COUNT(*) FROM Asistencia WHERE Fecha BETWEEN ? AND ?", periodo_inicio, periodo_fin)
    total_marcas_empresa = cursor.fetchone()[0]
    if total_marcas_empresa == 0:
        return 0 # Si nadie marcó en toda la empresa, no penalizamos asumiendo que no usaron el kiosco.
        
    # 2. Contar días con marca de asistencia
    cursor.execute("""
        SELECT COUNT(DISTINCT Fecha) 
        FROM Asistencia 
        WHERE EmpleadoID = ? AND Fecha BETWEEN ? AND ?
    """, empleado_id, periodo_inicio, periodo_fin)
    dias_asistidos = cursor.fetchone()[0]
    
    # 3. Contar días de licencia justificada
    cursor.execute("""
        SELECT FechaInicio, FechaFin, TipoLicencia 
        FROM LicenciasEmpleados 
        WHERE EmpleadoID = ? AND (FechaInicio <= ? AND FechaFin >= ?)
    """, empleado_id, periodo_fin, periodo_inicio)
    licencias = cursor.fetchall()
    
    dias_ya_contados_licencia = set()
    for lic in licencias:
        f_ini = max(periodo_inicio, lic.FechaInicio)
        f_fin = min(periodo_fin, lic.FechaFin)
        for i in range((f_fin - f_ini).days + 1):
            dia_actual = f_ini + timedelta(days=i)
            if dia_actual.weekday() != 6: # Si no es domingo
                dias_ya_contados_licencia.add(dia_actual)
    
    dias_justificados = len(dias_ya_contados_licencia)
    
    # 4. Cálculo final de ausencias injustificadas
    ausencias_injustificadas = max(0, dias_laborables_esperados - dias_asistidos - dias_justificados)
    return ausencias_injustificadas

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
    
    # Nuevos parámetros (Ley 185)
    dias_ausentes = float(amount(datos.get('dias_ausentes', 0),maximum=31))
    dias_feriados_trabajados = float(amount(datos.get('dias_feriados_trabajados', 0),maximum=31))

    if not all([empleado_id, periodo_inicio, periodo_fin]):
        return jsonify({'error': 'Faltan datos del período'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        validar_periodo_nomina(cursor,empleado_id,periodo_inicio,periodo_fin)
        if 'dias_ausentes' not in datos:
            # Si el usuario no especificó manualmente días ausentes, calcular automático
            dias_ausentes = obtener_dias_ausentes_auto(cursor, empleado_id, periodo_inicio, periodo_fin)
            
        cursor.execute("SELECT * FROM Empleados WHERE ID = ? AND EstadoEmpleado = 'Activo'", int(empleado_id))
        emp = cursor.fetchone()
        if not emp:
            return jsonify({'error': 'Empleado no encontrado o inactivo'}), 404

        salario_base = float(emp.SalarioBase)
        salario_diario = salario_base / 30

        cursor.execute("SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')")
        config = {r.Clave: r.Valor for r in cursor.fetchall()}

        tasa_inss_laboral = float(config.get('inss_laboral', '7.00'))

        cursor.execute("SELECT COUNT(*) FROM Empleados WHERE EstadoEmpleado = 'Activo'")
        total_empleados = cursor.fetchone()[0]
        tasa_inss_patronal = float(config.get('inss_patronal_mas50', '22.50')) if total_empleados >= 50 else float(config.get('inss_patronal_menos50', '21.50'))
        tasa_inatec = float(config.get('inatec', '2.00'))

        hora_ordinaria = salario_diario / 8
        monto_horas_extras = horas_extras * hora_ordinaria * 2 # Recargo del 100% (Art. 62 Ley 185)
        
        # Feriados Trabajados (Art. 66 Ley 185)
        monto_feriados = dias_feriados_trabajados * salario_diario

        # Deducciones por ausencias (Incluye proporcional del 7mo día: Art. 64 Ley 185)
        # Factor 1.1667 equivale a 1 día de falta + 1/6 del domingo
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
            cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)
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

        salario_base_efectivo=float(amount(salario_base_efectivo, 'Salario efectivo'))
        monto_horas_extras=float(amount(monto_horas_extras))
        otros_ingresos=float(amount(otros_ingresos))
        monto_feriados=float(amount(monto_feriados))
        total_devengado=amount(salario_base_efectivo)+amount(monto_horas_extras)+amount(otros_ingresos)+amount(monto_feriados)
        inss_laboral=amount(inss_laboral); ir_mensual=amount(ir_mensual)
        pension_alimenticia=amount(pension_alimenticia); vales_descontados=amount(vales_descontados)
        total_deducciones=inss_laboral+ir_mensual+pension_alimenticia+vales_descontados
        salario_neto=amount(total_devengado-total_deducciones, 'Salario neto')
        inss_patronal=amount(inss_patronal); inatec=amount(inatec)
        if total_devengado <= 0:
            raise ValueError('Revise las ausencias: no hay salario devengado para contabilizar.')

        cursor.execute("""
            INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Contabilizada', ?)
        """,
            int(empleado_id), periodo_inicio, periodo_fin, salario_base_efectivo,
            horas_extras, monto_horas_extras, (otros_ingresos + monto_feriados), total_devengado,
            inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
            total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
        )
        nomina_id = cursor.fetchone()[0]

        if vales_descontados > 0 and emp.UsuarioID:
            cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)

        # ============================================================
        # INTEGRACIÓN CONTABLE NIIF
        # ============================================================
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
            fecha=datetime.fromisoformat(periodo_fin)
        )
        # ============================================================

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
        return jsonify(error=str(e)),400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/liquidacion/calcular', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_liquidacion():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    fecha_egreso = datos.get('fecha_egreso')
    motivo = datos.get('motivo', 'Renuncia Voluntaria')

    if not all([empleado_id, fecha_egreso]):
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM Empleados WHERE ID = ?", int(empleado_id))
        emp = cursor.fetchone()
        if not emp:
            return jsonify({'error': 'Empleado no encontrado'}), 404

        fecha_ingreso = emp.FechaIngreso
        if type(fecha_ingreso) is str:
            fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
        elif hasattr(fecha_ingreso, 'date'):
            fecha_ingreso = fecha_ingreso.date()
            
        fecha_salida = datetime.strptime(fecha_egreso, '%Y-%m-%d').date()
        salario_base = float(emp.SalarioBase)
        salario_diario = salario_base / 30

        dias_trabajados = (fecha_salida - fecha_ingreso).days
        anios_completos = dias_trabajados // 365
        meses_fraccion = (dias_trabajados % 365) // 30
        
        dias_vacaciones_totales = dias_trabajados * (30 / 365)
        dias_vacaciones_pendientes = dias_vacaciones_totales

        cursor.execute("SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? ORDER BY PeriodoFin DESC", int(empleado_id))
        nominas_recientes = [float(r.SalarioBruto) for r in cursor.fetchall()]
        salario_promedio_6m = sum(nominas_recientes) / len(nominas_recientes) if nominas_recientes else salario_base
        salario_diario_vacaciones = salario_promedio_6m / 30

        monto_vacaciones = dias_vacaciones_pendientes * salario_diario_vacaciones
        inss_vacaciones = monto_vacaciones * 0.07

        salarios_6m = nominas_recientes
        salario_max_6m = max(salarios_6m) if salarios_6m else salario_base

        # Ciclo de Aguinaldo: 1 de diciembre al 30 de noviembre.
        if fecha_salida.month == 12:
            inicio_aguinaldo = date(fecha_salida.year, 12, 1)
        else:
            inicio_aguinaldo = date(fecha_salida.year - 1, 12, 1)
            
        inicio_aguinaldo_real = max(inicio_aguinaldo, fecha_ingreso)
        dias_aguinaldo = (fecha_salida - inicio_aguinaldo_real).days + 1
        
        aguinaldo_proporcional = salario_max_6m * (dias_aguinaldo / 365.0)

        aplica_indemnizacion = motivo in ['Despido Injustificado', 'Renuncia Voluntaria']

        dias_indemnizacion = 0
        if aplica_indemnizacion:
            anios_tramo1 = min(anios_completos, 3)
            dias_tramo1 = anios_tramo1 * 30

            anios_tramo2 = max(0, anios_completos - 3)
            dias_tramo2 = anios_tramo2 * 20

            dias_indemnizacion = dias_tramo1 + dias_tramo2

            if anios_completos < 3:
                dias_indemnizacion += meses_fraccion * 2.5
            else:
                dias_indemnizacion += meses_fraccion * 1.667

            dias_indemnizacion = min(dias_indemnizacion, 150)

        monto_indemnizacion = dias_indemnizacion * salario_diario
        ir_indemnizacion = 0
        if monto_indemnizacion > 500000:
            ir_indemnizacion = (monto_indemnizacion - 500000) * 0.15

        total_liquidacion = monto_vacaciones - inss_vacaciones + aguinaldo_proporcional + monto_indemnizacion - ir_indemnizacion

        conn.close()
        return jsonify({
            'status': 'success',
            'liquidacion': {
                'empleado': emp.NombreCompleto,
                'fecha_ingreso': fecha_ingreso.strftime('%d/%m/%Y'),
                'fecha_egreso': fecha_salida.strftime('%d/%m/%Y'),
                'dias_trabajados': dias_trabajados,
                'anios': anios_completos,
                'meses_fraccion': meses_fraccion,
                'salario_base': salario_base,
                'salario_diario': round(salario_diario, 2),
                'vacaciones': {
                    'dias': round(dias_vacaciones_pendientes, 2),
                    'salario_diario_usado': round(salario_diario_vacaciones, 2),
                    'monto_bruto': round(monto_vacaciones, 2),
                    'inss': round(inss_vacaciones, 2),
                    'neto': round(monto_vacaciones - inss_vacaciones, 2)
                },
                'aguinaldo': {
                    'salario_max_6m': salario_max_6m,
                    'dias_ciclo': dias_aguinaldo,
                    'monto': round(aguinaldo_proporcional, 2),
                    'nota': 'Exento de INSS e IR'
                },
                'indemnizacion': {
                    'aplica': aplica_indemnizacion,
                    'motivo': motivo,
                    'dias': round(dias_indemnizacion, 2),
                    'monto_bruto': round(monto_indemnizacion, 2),
                    'ir': round(ir_indemnizacion, 2),
                    'neto': round(monto_indemnizacion - ir_indemnizacion, 2),
                    'nota': 'Exento INSS. IR exento hasta C$500,000'
                },
                'total_liquidacion': round(total_liquidacion, 2)
            }
        })
    except Exception as e:
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500

@admin_bp.route('/rrhh/liquidacion/reporte', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def reporte_liquidacion():
    empleado_id = request.args.get('empleado_id')
    fecha_egreso = request.args.get('fecha_egreso')
    motivo = request.args.get('motivo', 'Renuncia Voluntaria')

    if not all([empleado_id, fecha_egreso]):
        flash('Faltan datos para generar el reporte.', 'error')
        return redirect(url_for('admin.rrhh'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM Empleados WHERE ID = ?", int(empleado_id))
        emp = cursor.fetchone()
        if not emp:
            flash('Empleado no encontrado', 'error')
            return redirect(url_for('admin.rrhh'))

        fecha_ingreso = emp.FechaIngreso
        if type(fecha_ingreso) is str:
            fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
        elif hasattr(fecha_ingreso, 'date'):
            fecha_ingreso = fecha_ingreso.date()
            
        fecha_salida = datetime.strptime(fecha_egreso, '%Y-%m-%d').date()
        salario_base = float(emp.SalarioBase)
        salario_diario = salario_base / 30

        dias_trabajados = (fecha_salida - fecha_ingreso).days
        anios_completos = dias_trabajados // 365
        meses_fraccion = (dias_trabajados % 365) // 30
        
        dias_vacaciones_totales = dias_trabajados * (30 / 365)
        dias_vacaciones_pendientes = dias_vacaciones_totales

        cursor.execute("SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? ORDER BY PeriodoFin DESC", int(empleado_id))
        nominas_recientes = [float(r.SalarioBruto) for r in cursor.fetchall()]
        salario_promedio_6m = sum(nominas_recientes) / len(nominas_recientes) if nominas_recientes else salario_base
        salario_diario_vacaciones = salario_promedio_6m / 30

        monto_vacaciones = dias_vacaciones_pendientes * salario_diario_vacaciones
        inss_vacaciones = monto_vacaciones * 0.07

        salarios_6m = nominas_recientes
        salario_max_6m = max(salarios_6m) if salarios_6m else salario_base

        if fecha_salida.month == 12:
            inicio_aguinaldo = date(fecha_salida.year, 12, 1)
        else:
            inicio_aguinaldo = date(fecha_salida.year - 1, 12, 1)
            
        inicio_aguinaldo_real = max(inicio_aguinaldo, fecha_ingreso)
        dias_aguinaldo = (fecha_salida - inicio_aguinaldo_real).days + 1
        
        aguinaldo_proporcional = salario_max_6m * (dias_aguinaldo / 365.0)

        aplica_indemnizacion = motivo in ['Despido Injustificado', 'Renuncia Voluntaria']

        dias_indemnizacion = 0
        if aplica_indemnizacion:
            anios_tramo1 = min(anios_completos, 3)
            dias_tramo1 = anios_tramo1 * 30

            anios_tramo2 = max(0, anios_completos - 3)
            dias_tramo2 = anios_tramo2 * 20

            dias_indemnizacion = dias_tramo1 + dias_tramo2

            if anios_completos < 3:
                dias_indemnizacion += meses_fraccion * 2.5
            else:
                dias_indemnizacion += meses_fraccion * 1.667

            dias_indemnizacion = min(dias_indemnizacion, 150)

        monto_indemnizacion = dias_indemnizacion * salario_diario
        ir_indemnizacion = 0
        if monto_indemnizacion > 500000:
            ir_indemnizacion = (monto_indemnizacion - 500000) * 0.15

        total_liquidacion = monto_vacaciones - inss_vacaciones + aguinaldo_proporcional + monto_indemnizacion - ir_indemnizacion

        liquidacion_data = {
            'empleado': emp.NombreCompleto,
            'fecha_ingreso': fecha_ingreso.strftime('%d/%m/%Y'),
            'fecha_egreso': fecha_salida.strftime('%d/%m/%Y'),
            'dias_trabajados': dias_trabajados,
            'anios': anios_completos,
            'meses_fraccion': meses_fraccion,
            'salario_base': salario_base,
            'salario_diario': round(salario_diario, 2),
            'vacaciones': {
                'dias': round(dias_vacaciones_pendientes, 2),
                'salario_diario_usado': round(salario_diario_vacaciones, 2),
                'monto_bruto': round(monto_vacaciones, 2),
                'inss': round(inss_vacaciones, 2),
                'neto': round(monto_vacaciones - inss_vacaciones, 2)
            },
            'aguinaldo': {
                'salario_max_6m': salario_max_6m,
                'dias_ciclo': dias_aguinaldo,
                'monto': round(aguinaldo_proporcional, 2),
                'nota': 'Exento de INSS e IR'
            },
            'indemnizacion': {
                'aplica': aplica_indemnizacion,
                'motivo': motivo,
                'dias': round(dias_indemnizacion, 2),
                'monto_bruto': round(monto_indemnizacion, 2),
                'ir': round(ir_indemnizacion, 2),
                'neto': round(monto_indemnizacion - ir_indemnizacion, 2),
                'nota': 'Exento INSS. IR exento hasta C$500,000'
            },
            'total_liquidacion': round(total_liquidacion, 2),
            'motivo': motivo
        }

        return render_template('admin/colilla_liquidacion.html', liquidacion=liquidacion_data, emp=emp, datetime=datetime)
    except Exception as e:
        import logging
        logging.error(f"Internal server error: {e}")
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
        cursor.execute("SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')")
        config = {r.Clave: r.Valor for r in cursor.fetchall()}
        
        tasa_inss_laboral = float(config.get('inss_laboral', '7.00'))
        tasa_inatec = float(config.get('inatec', '2.00'))
        tabla_ir = json.loads(config.get('ir_tabla', '[]'))
        
        cursor.execute("SELECT * FROM Empleados WHERE EstadoEmpleado = 'Activo'")
        empleados = cursor.fetchall()
        total_empleados = len(empleados)
        
        if total_empleados == 0:
            return jsonify({'error': 'No hay empleados activos para procesar'}), 400
            
        tasa_inss_patronal = float(config.get('inss_patronal_mas50', '22.50')) if total_empleados >= 50 else float(config.get('inss_patronal_menos50', '21.50'))
        
        nomina_ids = []
        for emp in empleados:
            validar_periodo_nomina(cursor,emp.ID,periodo_inicio,periodo_fin)
            salario_base = float(emp.SalarioBase)
            salario_diario = salario_base / 30
            
            # Cálculo automático de ausencias
            dias_ausentes = obtener_dias_ausentes_auto(cursor, emp.ID, periodo_inicio, periodo_fin)
            # Factor 1.1667 equivale a 1 día de falta + 1/6 del domingo proporcional (Ley 185)
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
                cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)
                vales_descontados = float(cursor.fetchone()[0])
            
            salario_neto_pre = total_devengado - inss_laboral - ir_mensual
            pension_alimenticia = calcular_deducciones_judiciales(
                cursor, emp.ID, salario_neto_pre, periodo_fin
            )
            
            total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
            salario_neto = total_devengado - total_deducciones
            
            inss_patronal = total_devengado * (tasa_inss_patronal / 100)
            inatec = total_devengado * (tasa_inatec / 100)
            
            salario_base_efectivo=amount(salario_base_efectivo)
            total_devengado=salario_base_efectivo
            inss_laboral=amount(inss_laboral); ir_mensual=amount(ir_mensual)
            pension_alimenticia=amount(pension_alimenticia); vales_descontados=amount(vales_descontados)
            total_deducciones=inss_laboral+ir_mensual+pension_alimenticia+vales_descontados
            salario_neto=amount(total_devengado-total_deducciones, 'Salario neto')
            inss_patronal=amount(inss_patronal); inatec=amount(inatec)
            if total_devengado <= 0:
                raise ValueError(f'Revise las ausencias de {emp.NombreCompleto}: no hay salario devengado.')

            cursor.execute("""
                INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                    HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                    INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                    TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Contabilizada', ?)
            """,
                emp.ID, periodo_inicio, periodo_fin, salario_base_efectivo, total_devengado,
                inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
                total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
            )
            nomina_id = cursor.fetchone()[0]
            nomina_ids.append(nomina_id)
            from app.services.contabilidad_service import ContabilidadService
            ContabilidadService.contabilizar_nomina(cursor, current_user.id, nomina_id,
                emp.NombreCompleto, total_devengado, inss_laboral, ir_mensual,
                inss_patronal, inatec, pension_alimenticia, vales_descontados,
                salario_neto, emp.Cargo, request.remote_addr,fecha=datetime.fromisoformat(periodo_fin))
            
            if vales_descontados > 0 and emp.UsuarioID:
                cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Planilla generada para {total_empleados} empleados.'})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
        cursor.execute("SELECT * FROM Empleados WHERE EstadoEmpleado = 'Activo'")
        empleados = cursor.fetchall()
        total_empleados = len(empleados)
        
        if total_empleados == 0:
            return jsonify({'error': 'No hay empleados activos para procesar'}), 400
            
        fecha_fin_ciclo = date(anio, 11, 30)
        fecha_inicio_ciclo = date(anio - 1, 12, 1)
        
        for emp in empleados:
            validar_periodo_nomina(cursor,emp.ID,date(anio-1,12,1),date(anio,11,30),aguinaldo=True)
            fecha_ingreso = emp.FechaIngreso
            if type(fecha_ingreso) is str:
                fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
            elif hasattr(fecha_ingreso, 'date'):
                fecha_ingreso = fecha_ingreso.date()
                
            cursor.execute("SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? AND PeriodoFin <= ? ORDER BY PeriodoFin DESC", (emp.ID, fecha_fin_ciclo.strftime('%Y-%m-%d')))
            nominas_recientes = [float(r.SalarioBruto) for r in cursor.fetchall()]
            salario_base = float(emp.SalarioBase)
            salario_max_6m = max(nominas_recientes) if nominas_recientes else salario_base
            
            inicio_aguinaldo_real = max(fecha_inicio_ciclo, fecha_ingreso)
            
            # Solo calcular si ingresó antes del 30 de noviembre del año actual
            if inicio_aguinaldo_real <= fecha_fin_ciclo:
                dias_aguinaldo = (fecha_fin_ciclo - inicio_aguinaldo_real).days + 1
                aguinaldo_proporcional = salario_max_6m * (dias_aguinaldo / 365.0)
                
                cursor.execute("""
                    INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                        HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                        INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                        TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?, 0, 0, 0, 0, 0, ?, 0, 0, 'Borrador', ?)
                """,
                    emp.ID, fecha_inicio_ciclo.strftime('%Y-%m-%d'), fecha_fin_ciclo.strftime('%Y-%m-%d'),
                    aguinaldo_proporcional, aguinaldo_proporcional, aguinaldo_proporcional, current_user.id
                )

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Planilla de Aguinaldo generada para {total_empleados} empleados.'})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error in aguinaldo batch: {e}")
        return jsonify({'error': f'Error procesando aguinaldo: {str(e)}'}), 500
    finally:
        conn.close()

@admin_bp.route('/rrhh/nomina/<int:nomina_id>/colilla')
@login_required
@roles_required('Admin', 'SuperAdmin')
def colilla_pago(nomina_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, e.NombreCompleto, e.Cargo, e.Cedula, e.NumeroINSS, e.FechaIngreso
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE n.ID = ?
    """, nomina_id)
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
    
    cursor.execute("""
        SELECT e.NombreCompleto, e.NumeroINSS, n.TotalDevengado, n.INSSLaboral, n.INSSPatronal, n.INATEC
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE MONTH(n.PeriodoInicio) = ? AND YEAR(n.PeriodoInicio) = ?
    """, int(mes), int(anio))
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
    
    cursor.execute("""
        SELECT e.NombreCompleto, e.Cedula, e.FechaIngreso, n.PeriodoFin, n.OtrosIngresos AS AguinaldoMonto
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE YEAR(n.PeriodoFin) = ? AND n.SalarioBruto = 0 AND n.OtrosIngresos > 0
        ORDER BY e.NombreCompleto
    """, int(anio))
    
    nominas_aguinaldo = cursor.fetchall()
    
    registros = []
    total_aguinaldo = 0
    
    for n in nominas_aguinaldo:
        # Reconstruct calculations
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
    
    cursor.execute("""
        SELECT NombreCompleto, FechaNacimiento
        FROM Empleados
        WHERE EstadoEmpleado = 'Activo' AND FechaNacimiento IS NOT NULL
          AND DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()), FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE())
           OR DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()) + 1, FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE())
    """)
    cumples = [{'nombre': r.NombreCompleto, 'fecha': r.FechaNacimiento.strftime('%d/%m')} for r in cursor.fetchall()]
    
    cursor.execute("""
        SELECT NombreCompleto, FechaFinContrato, TipoContrato
        FROM Empleados
        WHERE EstadoEmpleado = 'Activo' 
          AND TipoContrato = 'Determinado'
          AND FechaFinContrato IS NOT NULL
          AND FechaFinContrato BETWEEN GETDATE() AND DATEADD(day, 30, GETDATE())
    """)
    contratos = [{'nombre': r.NombreCompleto, 'fecha': r.FechaFinContrato.strftime('%d/%m/%Y')} for r in cursor.fetchall()]
    
    conn.close()
    return jsonify({'cumpleanos': cumples, 'contratos': contratos})

@admin_bp.route('/api/rrhh/empleados/referencias', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def get_empleados_referencias():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ID, NombreCompleto, FotoPerfil FROM Empleados WHERE EstadoEmpleado = 'Activo' AND FotoPerfil IS NOT NULL")
    empleados = [{'id': r.ID, 'nombre': r.NombreCompleto, 'foto': r.FotoPerfil} for r in cursor.fetchall()]
    conn.close()
    return jsonify(empleados)


# La ruta del kiosco fue movida al blueprint app.kiosco (accesible en /kiosco/)


@admin_bp.route('/api/rrhh/kiosco/marcar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def kiosco_marcar():
    datos = request.json
    cedula = datos.get('cedula')
    empleado_id = datos.get('empleado_id')
    tipo = datos.get('tipo')
    fecha = datetime.now().strftime('%Y-%m-%d')
    hora = datetime.now().strftime('%H:%M:%S')
    
    if (not cedula and not empleado_id) or not tipo:
        return jsonify({'error': 'Faltan datos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if empleado_id:
            cursor.execute("SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM Empleados WHERE ID = ? AND EstadoEmpleado = 'Activo'", empleado_id)
        else:
            cursor.execute("SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM Empleados WHERE Cedula = ? AND EstadoEmpleado = 'Activo'", cedula)
            
        empleado = cursor.fetchone()
        if not empleado:
            return jsonify({'error': 'Cédula no encontrada o empleado inactivo'}), 404
            
        empleado_id = empleado.ID
        nombre = empleado.NombreCompleto
        
        cursor.execute("SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos FROM TurnosLaborales WHERE Activo = 1")
        turno = cursor.fetchone()
        turno_id = turno.ID if turno else 1
        
        cursor.execute("SELECT ID, HoraEntrada, HoraSalida FROM Asistencia WHERE EmpleadoID = ? AND Fecha = ?", empleado_id, fecha)
        asistencia = cursor.fetchone()
        
        if tipo == 'entrada':
            if asistencia and asistencia.HoraEntrada:
                return jsonify({'error': f'Hola {nombre}, ya tienes entrada registrada hoy.'}), 400
                
            estado_entrada = 'A Tiempo'
            from datetime import datetime as dt, timedelta
            
            # Determinar hora de entrada límite usando horario personalizado o general
            if empleado.HoraEntrada:
                hora_limite = (dt.combine(dt.today(), empleado.HoraEntrada) + timedelta(minutes=15)).time() # 15 mins tolerancia por defecto para personalizados
            elif turno:
                hora_limite = (dt.combine(dt.today(), turno.HoraEntrada) + timedelta(minutes=turno.ToleranciaMinutos)).time()
            else:
                hora_limite = None

            if hora_limite:
                hora_actual = dt.now().time()
                if hora_actual > hora_limite:
                    estado_entrada = 'Llegada Tardia'
            
            if not asistencia:
                cursor.execute("""
                    INSERT INTO Asistencia (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, empleado_id, turno_id, fecha, hora, estado_entrada, current_user.id)
            else:
                cursor.execute("""
                    UPDATE Asistencia SET HoraEntrada = ?, EstadoEntrada = ?, TurnoID = ?, RegistradoPor = ?
                    WHERE ID = ?
                """, hora, estado_entrada, turno_id, current_user.id, asistencia.ID)
                
            msg = f"¡Bienvenido {nombre}! Entrada registrada."
            
        elif tipo == 'salida':
            if not asistencia or not asistencia.HoraEntrada:
                return jsonify({'error': 'No puedes registrar salida sin haber marcado entrada.'}), 400
            if asistencia.HoraSalida:
                return jsonify({'error': f'Adiós {nombre}, ya tenías tu salida registrada hoy.'}), 400
                
            cursor.execute("UPDATE Asistencia SET HoraSalida = ? WHERE ID = ?", hora, asistencia.ID)
            msg = f"¡Adiós {nombre}! Salida registrada."
            
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': msg})
        
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
        # Get active employees
        cursor.execute("SELECT ID, NombreCompleto, Cargo FROM Empleados WHERE EstadoEmpleado = 'Activo'")
        empleados = cursor.fetchall()
        total_esperados = len(empleados)
        
        # Get attendance for the selected date
        cursor.execute("""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, t.Nombre AS Turno
            FROM Asistencia a
            LEFT JOIN TurnosLaborales t ON a.TurnoID = t.ID
            WHERE a.Fecha = ?
        """, (fecha_str,))
        
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
                # Convertir obj a str si no es None
                try:
                    entrada = registro.HoraEntrada.strftime('%H:%M:%S') if registro.HoraEntrada else '--:--'
                except:
                    entrada = str(registro.HoraEntrada)
                try:
                    salida = registro.HoraSalida.strftime('%H:%M:%S') if registro.HoraSalida else '--:--'
                except:
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
        
        # Ordenar (Ausentes arriba, luego Tardes, luego A Tiempo)
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
        cursor.execute("SELECT ID, NombreCompleto, Cargo FROM Empleados WHERE EstadoEmpleado = 'Activo'")
        empleados = cursor.fetchall()
        total_esperados = len(empleados)
        
        cursor.execute("""
            SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, t.Nombre AS Turno
            FROM Asistencia a
            LEFT JOIN TurnosLaborales t ON a.TurnoID = t.ID
            WHERE a.Fecha = ?
        """, (fecha_str,))
        
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
                except:
                    entrada = str(registro.HoraEntrada)
                try:
                    salida = registro.HoraSalida.strftime('%H:%M:%S') if registro.HoraSalida else '--:--'
                except:
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
