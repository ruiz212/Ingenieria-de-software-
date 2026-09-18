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
from datetime import datetime

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
            'consentimiento': bool(r.ConsentimientoDatos)
        })

    # Nóminas recientes
    cursor.execute("""
        SELECT TOP 20 n.ID, e.NombreCompleto, n.PeriodoInicio, n.PeriodoFin,
               n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto, n.Estado
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        ORDER BY n.FechaGeneracion DESC
    """)
    nominas = [{
        'id': r.ID, 'empleado': r.NombreCompleto,
        'periodo': f"{r.PeriodoInicio.strftime('%d/%m')} - {r.PeriodoFin.strftime('%d/%m/%Y')}",
        'devengado': float(r.TotalDevengado), 'deducciones': float(r.TotalDeducciones),
        'neto': float(r.SalarioNeto), 'estado': r.Estado
    } for r in cursor.fetchall()]

    # Configuraciones de tasas
    cursor.execute("SELECT Clave, Valor FROM ConfiguracionSistema WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla')")
    tasas = {r.Clave: r.Valor for r in cursor.fetchall()}

    # Conteo de empleados activos (para determinar tasa patronal)
    cursor.execute("SELECT COUNT(*) FROM Empleados WHERE EstadoEmpleado = 'Activo'")
    total_activos = cursor.fetchone()[0]

    # Asistencia de hoy
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada 
        FROM Asistencia a 
        WHERE a.Fecha = ?
    """, fecha_hoy)
    asistencia_hoy = {r.EmpleadoID: {'entrada': r.HoraEntrada.strftime('%H:%M') if r.HoraEntrada else None, 
                                     'salida': r.HoraSalida.strftime('%H:%M') if r.HoraSalida else None,
                                     'estado': r.EstadoEntrada} 
                      for r in cursor.fetchall()}

    conn.close()

    return render_template('admin/rrhh.html', user=current_user,
        empleados=empleados, nominas=nominas, tasas=tasas, total_activos=total_activos,
        asistencia_hoy=asistencia_hoy, datetime=datetime)


@admin_bp.route('/api/rrhh/empleado', methods=['POST'])
@csrf.exempt
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
        if 'foto' in datos and datos['foto']:
            # Format: "data:image/jpeg;base64,/9j/4AAQ..."
            try:
                header, encoded = datos['foto'].split(",", 1)
                ext = "png" if "png" in header else "jpg"
                filename = f"face_{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(current_app.root_path, 'static', 'uploads', 'faces', filename)
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(encoded))
                foto_path = f"/static/uploads/faces/{filename}"
            except Exception as e:
                import logging
                logging.error(f"Error procesando foto: {e}")

        cursor.execute("""
            INSERT INTO Empleados (NombreCompleto, Cedula, FechaNacimiento, Genero, Direccion,
                Telefono, CorreoElectronico, NumeroINSS, Cargo, FechaIngreso, TipoContrato, FechaFinContrato,
                TipoJornada, SalarioBase, FormaPago, ConsentimientoDatos, FechaConsentimiento, FotoPerfil)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
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
            foto_path
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Empleado registrado'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/rrhh/nomina/calcular', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def calcular_nomina():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    periodo_inicio = datos.get('periodo_inicio')
    periodo_fin = datos.get('periodo_fin')
    horas_extras = float(datos.get('horas_extras', 0))
    otros_ingresos = float(datos.get('otros_ingresos', 0))

    if not all([empleado_id, periodo_inicio, periodo_fin]):
        return jsonify({'error': 'Faltan datos del período'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
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
        monto_horas_extras = horas_extras * hora_ordinaria * 2

        total_devengado = salario_base + monto_horas_extras + otros_ingresos

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
        pension_alimenticia = 0
        cursor.execute("SELECT PorcentajeSalarioNeto FROM DeduccionesJudiciales WHERE EmpleadoID = ? AND Activa = 1 AND TipoDeduccion = 'Pension Alimenticia'", int(empleado_id))
        deducciones_judiciales = cursor.fetchall()
        total_porcentaje_pension = sum(float(d.PorcentajeSalarioNeto) for d in deducciones_judiciales)
        if total_porcentaje_pension > 60:
            total_porcentaje_pension = 60
        pension_alimenticia = salario_neto_pre * (total_porcentaje_pension / 100)

        total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
        salario_neto = total_devengado - total_deducciones

        inss_patronal = total_devengado * (tasa_inss_patronal / 100)
        inatec = total_devengado * (tasa_inatec / 100)

        cursor.execute("""
            INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Borrador', ?)
        """,
            int(empleado_id), periodo_inicio, periodo_fin, salario_base,
            horas_extras, monto_horas_extras, otros_ingresos, total_devengado,
            inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
            total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
        )
        nomina_id = cursor.fetchone()[0]

        if vales_descontados > 0 and emp.UsuarioID:
            cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)

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
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

@admin_bp.route('/api/rrhh/liquidacion/calcular', methods=['POST'])
@csrf.exempt
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

        mes_actual = fecha_salida.month
        meses_ciclo = mes_actual
        aguinaldo_proporcional = salario_max_6m * (meses_ciclo / 12)

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
                    'meses_ciclo': meses_ciclo,
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

@admin_bp.route('/api/rrhh/nomina/calcular_batch', methods=['POST'])
@csrf.exempt
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
            salario_base = float(emp.SalarioBase)
            total_devengado = salario_base
            
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
            pension_alimenticia = 0
            cursor.execute("SELECT PorcentajeSalarioNeto FROM DeduccionesJudiciales WHERE EmpleadoID = ? AND Activa = 1 AND TipoDeduccion = 'Pension Alimenticia'", emp.ID)
            deducciones_judiciales = cursor.fetchall()
            total_porcentaje_pension = min(sum(float(d.PorcentajeSalarioNeto) for d in deducciones_judiciales), 60)
            pension_alimenticia = salario_neto_pre * (total_porcentaje_pension / 100)
            
            total_deducciones = inss_laboral + ir_mensual + pension_alimenticia + vales_descontados
            salario_neto = total_devengado - total_deducciones
            
            inss_patronal = total_devengado * (tasa_inss_patronal / 100)
            inatec = total_devengado * (tasa_inatec / 100)
            
            cursor.execute("""
                INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                    HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                    INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                    TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Borrador', ?)
            """,
                emp.ID, periodo_inicio, periodo_fin, salario_base, total_devengado,
                inss_laboral, ir_mensual, pension_alimenticia, vales_descontados,
                total_deducciones, salario_neto, inss_patronal, inatec, current_user.id
            )
            nomina_id = cursor.fetchone()[0]
            nomina_ids.append(nomina_id)
            
            if vales_descontados > 0 and emp.UsuarioID:
                cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 WHERE EmpleadoID = ? AND Descontado = 0", emp.UsuarioID)

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Planilla generada para {total_empleados} empleados.'})
        
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error in batch payroll: {e}")
        return jsonify({'error': 'Error procesando la planilla batch. Rollback ejecutado.'}), 500
    finally:
        conn.close()

@admin_bp.route('/rrhh/nomina/<int:nomina_id>/colilla')
@login_required
@roles_required('Admin', 'SuperAdmin')
def colilla_pago(nomina_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, e.NombreCompleto, e.Cargo, e.Cedula, e.NumeroINSS
        FROM Nomina n
        JOIN Empleados e ON n.EmpleadoID = e.ID
        WHERE n.ID = ?
    """, nomina_id)
    nomina = cursor.fetchone()
    conn.close()
    
    if not nomina:
        flash('Nómina no encontrada', 'error')
        return redirect(url_for('admin.rrhh'))
        
    return render_template('admin/colilla_pago.html', nomina=nomina, datetime=datetime)

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

@admin_bp.route('/rrhh/kiosco', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def kiosco_asistencia():
    return render_template('admin/kiosco.html')

@admin_bp.route('/api/rrhh/kiosco/marcar', methods=['POST'])
@csrf.exempt
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
            cursor.execute("SELECT ID, NombreCompleto FROM Empleados WHERE ID = ? AND EstadoEmpleado = 'Activo'", empleado_id)
        else:
            cursor.execute("SELECT ID, NombreCompleto FROM Empleados WHERE Cedula = ? AND EstadoEmpleado = 'Activo'", cedula)
            
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
            if turno:
                from datetime import datetime as dt, timedelta
                hora_limite = (dt.combine(dt.today(), turno.HoraEntrada) + timedelta(minutes=turno.ToleranciaMinutos)).time()
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
        
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal error in kiosco: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()