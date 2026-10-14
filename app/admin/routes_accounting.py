# app/admin/routes_accounting.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime
from app.services.validation import amount, required_text

@admin_bp.route('/contabilidad')
@login_required
@roles_required('Admin', 'SuperAdmin')
def contabilidad():
    """Módulo de Contabilidad Privada (Egresos y Vales)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Egresos Privados
    cursor.execute(
        "SELECT e.ID, e.Concepto, e.Monto, e.Fecha, u.NombreCompleto AS RegistradoPor "
        "FROM EgresosPrivados e "
        "JOIN Usuarios u ON e.UsuarioID = u.ID "
        "ORDER BY e.Fecha DESC"
    )
    egresos = [
        {'id': row.ID, 'concepto': row.Concepto, 'monto': float(row.Monto),
         'fecha': row.Fecha.strftime('%d/%m/%Y %H:%M'), 'registrado_por': row.RegistradoPor}
        for row in cursor.fetchall()
    ]

    # Vales a Empleados
    cursor.execute(
        "SELECT v.ID, u.NombreCompleto AS Empleado, v.Monto, v.Fecha, v.Descontado "
        "FROM ValesEmpleados v "
        "JOIN Usuarios u ON v.EmpleadoID = u.ID "
        "ORDER BY v.Fecha DESC"
    )
    vales = [
        {'id': row.ID, 'empleado': row.Empleado, 'monto': float(row.Monto),
         'fecha': row.Fecha.strftime('%d/%m/%Y %H:%M'), 'descontado': bool(row.Descontado)}
        for row in cursor.fetchall()
    ]

    # Lista de usuarios para el dropdown de vales
    cursor.execute("SELECT ID, NombreCompleto FROM Usuarios WHERE Activo = 1 ORDER BY NombreCompleto")
    empleados = [{'id': row.ID, 'nombre': row.NombreCompleto} for row in cursor.fetchall()]

    # Totales del MES actual
    # 1. Ingresos (Ventas)
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE EstadoFiscal='Emitida' AND MONTH(FechaHora) = MONTH(GETDATE()) AND YEAR(FechaHora) = YEAR(GETDATE())")
    ingresos_mes = float(cursor.fetchone()[0])

    # 2. Compras de Materia Prima
    cursor.execute("SELECT ISNULL(SUM(CostoTotal), 0) FROM ComprasMateriaPrima WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    compras_mes = float(cursor.fetchone()[0])

    # 3. Egresos Privados
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM EgresosPrivados WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    egresos_mes = float(cursor.fetchone()[0])

    # Totales del DIA actual
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE EstadoFiscal='Emitida' AND CONVERT(date, FechaHora) = CONVERT(date, GETDATE())")
    ingresos_hoy = float(cursor.fetchone()[0])

    cursor.execute("SELECT ISNULL(SUM(CostoTotal), 0) FROM ComprasMateriaPrima WHERE CONVERT(date, Fecha) = CONVERT(date, GETDATE())")
    compras_hoy = float(cursor.fetchone()[0])

    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM EgresosPrivados WHERE CONVERT(date, Fecha) = CONVERT(date, GETDATE())")
    egresos_hoy = float(cursor.fetchone()[0])

    # Vales Pendientes
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE Descontado = 0")
    total_vales_pendientes = float(cursor.fetchone()[0])

    conn.close()

    metricas = {
        'ingresos_mes': ingresos_mes,
        'compras_mes': compras_mes,
        'egresos_mes': egresos_mes,
        'balance_mes': ingresos_mes - compras_mes - egresos_mes,
        'ingresos_hoy': ingresos_hoy,
        'compras_hoy': compras_hoy,
        'egresos_hoy': egresos_hoy,
        'balance_hoy': ingresos_hoy - compras_hoy - egresos_hoy,
        'total_vales_pendientes': total_vales_pendientes
    }

    return render_template('admin/contabilidad.html', user=current_user, egresos=egresos, vales=vales, empleados=empleados, metricas=metricas)


@admin_bp.route('/api/contabilidad/egresos', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_egreso():
    datos = request.json
    concepto = required_text(datos.get('concepto'), 'Concepto', 255)
    monto = amount(datos.get('monto'), 'Monto', minimum=0.01)

    if not concepto or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO EgresosPrivados (Concepto, Monto, UsuarioID) OUTPUT INSERTED.ID VALUES (?, ?, ?)",
            concepto, float(monto), current_user.id
        )
        new_id = cursor.fetchone()[0]

        # ============================================================
        # INTEGRACIÓN CONTABLE NIIF
        # ============================================================
        from app.services.contabilidad_service import ContabilidadService
        ContabilidadService.contabilizar_egreso(
            cursor=cursor,
            usuario_id=current_user.id,
            concepto=concepto,
            monto=float(monto),
            referencia=f"EGR-{new_id}",
            ip=request.remote_addr
        )
        # ============================================================

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Egreso registrado y contabilizado', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/contabilidad/vales', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_vale():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    monto = amount(datos.get('monto'), 'Monto', minimum=0.01)

    if not empleado_id or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ValesEmpleados (EmpleadoID, Monto, Fecha) OUTPUT INSERTED.ID VALUES (?, ?, GETDATE())",
            int(empleado_id), float(monto)
        )
        new_id = cursor.fetchone()[0]

        # Necesitamos el nombre del empleado para la glosa
        cursor.execute("SELECT NombreCompleto FROM Usuarios WHERE ID = ?", (int(empleado_id),))
        emp_nombre = cursor.fetchone()[0]

        # ============================================================
        # INTEGRACIÓN CONTABLE NIIF
        # ============================================================
        from app.services.contabilidad_service import ContabilidadService
        ContabilidadService.contabilizar_vale(
            cursor=cursor,
            usuario_id=current_user.id,
            empleado_nombre=emp_nombre,
            monto=float(monto),
            referencia=f"VALE-{new_id}",
            ip=request.remote_addr
        )
        # ============================================================

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Vale registrado y contabilizado', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/contabilidad/vales/<int:vale_id>/toggle', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_vale(vale_id):
    return jsonify(error='Los vales se descuentan al contabilizar la nómina. Una corrección requiere un ajuste contable.'),409


# ============================================================
# MÓDULO DE PARTIDA DOBLE (CONTABILIDAD CORE)
# ============================================================

import decimal

@admin_bp.route('/contabilidad/balance', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def balance_general():
    conn = get_db_connection()
    cursor = conn.cursor()

    fecha_corte = request.args.get('fecha_corte', datetime.now().strftime('%Y-%m-%d'))

    # 1. Consulta con CTE para obtener Saldos Finales de TODAS las cuentas
    sql_balance = """
    WITH SaldosHistoricos AS (
        SELECT
            C.Clase,
            C.Grupo,
            C.Codigo,
            C.Nombre AS Cuenta,
            C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM DetalleAsientos D
        JOIN AsientosDiario A ON D.AsientoID = A.ID
        JOIN CatalogoCuentas C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND A.Fecha < DATEADD(day,1,CAST(? AS date))
        GROUP BY C.Clase, C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase,
        Grupo,
        Codigo,
        Cuenta,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (TotalDebe - TotalHaber)
            ELSE (TotalHaber - TotalDebe)
        END AS SaldoFinal
    FROM SaldosHistoricos
    WHERE (TotalDebe - TotalHaber) != 0
    ORDER BY Codigo;
    """

    cursor.execute(sql_balance, (fecha_corte,))
    cuentas = cursor.fetchall()
    conn.close()

    # Organizar resultados
    activos = []
    pasivos = []
    capital = []

    total_activos = 0
    total_pasivos = 0
    total_capital = 0
    utilidad_ejercicio = 0

    for row in cuentas:
        cuenta_obj = {
            'Codigo': row.Codigo,
            'Cuenta': row.Cuenta,
            'SaldoFinal': float(row.SaldoFinal)
        }

        if row.Clase == 'Activo':
            activos.append(cuenta_obj)
            total_activos += cuenta_obj['SaldoFinal']
        elif row.Clase == 'Pasivo':
            pasivos.append(cuenta_obj)
            total_pasivos += cuenta_obj['SaldoFinal']
        elif row.Clase == 'Capital':
            capital.append(cuenta_obj)
            total_capital += cuenta_obj['SaldoFinal']
        elif row.Clase == 'Ingreso':
            utilidad_ejercicio += cuenta_obj['SaldoFinal']
        elif row.Clase == 'Costo':
            utilidad_ejercicio -= cuenta_obj['SaldoFinal']
        elif row.Clase == 'Gasto':
            utilidad_ejercicio -= cuenta_obj['SaldoFinal']

    # Agregar la Utilidad del Ejercicio al Capital (Ecuación contable ampliada)
    if utilidad_ejercicio != 0:
        capital.append({
            'Codigo': '3.X',
            'Cuenta': 'Utilidad (Pérdida) del Ejercicio en Curso',
            'SaldoFinal': utilidad_ejercicio
        })
        total_capital += utilidad_ejercicio

    if request.args.get('print') == '1':
        return render_template('admin/balance_imprimir.html',
                               fecha_corte=fecha_corte,
                               activos=activos, total_activos=total_activos,
                               pasivos=pasivos, total_pasivos=total_pasivos,
                               capital=capital, total_capital=total_capital,
                               datetime=datetime)

    return render_template('admin/balance_general.html',
                           user=current_user,
                           fecha_corte=fecha_corte,
                           activos=activos, total_activos=total_activos,
                           pasivos=pasivos, total_pasivos=total_pasivos,
                           capital=capital, total_capital=total_capital)


@admin_bp.route('/contabilidad/asiento', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_asiento():
    from app.services.contabilidad_service import ContabilidadError
    data=request.get_json()
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        fecha=datetime.fromisoformat(data.get('fecha',datetime.now().isoformat()))
        cursor.execute('SELECT Mes,Anio FROM PeriodosContables WHERE ID=?',data.get('periodo_id'))
        period=cursor.fetchone()
        if not period:
            raise ValueError('Seleccione un período existente.')
        lines=[]
        for detail in data.get('detalles',[]):
            cursor.execute('SELECT Codigo FROM CatalogoCuentas WHERE ID=?',detail.get('cuenta_id'))
            account=cursor.fetchone()
            if not account:
                raise ValueError('Cuenta no encontrada.')
            lines.append((account[0],detail.get('debe',0),detail.get('haber',0)))
        result=ContabilidadService.crear_asiento(cursor,data.get('descripcion'),lines,current_user.id,
            referencia_externa=data.get('referencia'),mes=period.Mes,anio=period.Anio,fecha=fecha,ip=request.remote_addr)
        from app.services.fiscal_service import audit
        audit(cursor,current_user.id,'ASIENTO_MANUAL','Asiento',result['asiento_id'],result,request.remote_addr)
        conn.commit()
        return jsonify(success=True,**result)
    except (ValueError,ContabilidadError) as error:
        conn.rollback(); return jsonify(error=str(error)),400
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


@admin_bp.route('/contabilidad/cierre-periodo', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def cierre_periodo():
    from app.services.contabilidad_service import ContabilidadError
    from app.services.fiscal_service import audit
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        data=request.get_json() if request.is_json else request.form
        period=int(data.get('periodo_id',0))
        ContabilidadService.cerrar_periodo(cursor,period,current_user.id)
        audit(cursor,current_user.id,'CIERRE_MENSUAL','Periodo',period,{},request.remote_addr)
        conn.commit()
        flash('Período cerrado. Ya no admite nuevos asientos.','success')
        if request.is_json:
            return jsonify(success=True)
    except (ValueError,ContabilidadError) as error:
        conn.rollback()
        if request.is_json:
            return jsonify(error=str(error)),400
        flash(str(error),'error')
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return redirect(url_for('admin.fiscal'))

@admin_bp.route('/contabilidad/estado-resultados', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def estado_resultados():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Por defecto, filtramos por el mes y año actual
    mes = request.args.get('mes', datetime.now().month)
    anio = request.args.get('anio', datetime.now().year)

    # 1. Obtener el PeriodoID correspondiente
    cursor.execute("SELECT ID FROM PeriodosContables WHERE Mes = ? AND Anio = ?", (mes, anio))
    periodo_row = cursor.fetchone()

    if not periodo_row:
        flash(f'No hay un periodo contable creado para {mes}/{anio}.', 'warning')
        return render_template('admin/estado_resultados.html',
                               user=current_user,
                               mes=mes, anio=anio,
                               ingresos=[], costos=[], gastos=[],
                               total_ingresos=0, total_costos=0, total_gastos=0,
                               utilidad_bruta=0, utilidad_neta=0)

    periodo_id = periodo_row[0]

    # 2. Consulta con CTE para obtener Saldos de Ingresos, Costos y Gastos
    sql_resultados = """
    WITH MovimientosResultados AS (
        SELECT
            C.Clase,
            C.Codigo,
            C.Nombre AS Cuenta,
            C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM DetalleAsientos D
        JOIN AsientosDiario A ON D.AsientoID = A.ID
        JOIN CatalogoCuentas C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND C.Clase IN ('Ingreso', 'Costo', 'Gasto')
          AND A.PeriodoID = ?
        GROUP BY C.Clase, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase,
        Codigo,
        Cuenta,
        CASE
            WHEN Naturaleza = 'Acreedora' THEN (TotalHaber - TotalDebe)
            ELSE (TotalDebe - TotalHaber)
        END AS SaldoNeto
    FROM MovimientosResultados
    WHERE (TotalDebe - TotalHaber) != 0
    ORDER BY
        CASE WHEN Clase = 'Ingreso' THEN 1
             WHEN Clase = 'Costo' THEN 2
             ELSE 3 END, Codigo;
    """

    cursor.execute(sql_resultados, (periodo_id,))
    cuentas = cursor.fetchall()
    conn.close()

    # Organizar resultados
    ingresos = []
    costos = []
    gastos = []

    total_ingresos = 0
    total_costos = 0
    total_gastos = 0

    for row in cuentas:
        cuenta_obj = {
            'Codigo': row.Codigo,
            'Cuenta': row.Cuenta,
            'SaldoNeto': float(row.SaldoNeto)
        }

        # Categorizar estrictamente según Clase NIIF
        if row.Clase == 'Ingreso':
            ingresos.append(cuenta_obj)
            total_ingresos += cuenta_obj['SaldoNeto']
        elif row.Clase == 'Costo':
            costos.append(cuenta_obj)
            total_costos += cuenta_obj['SaldoNeto']
        else:
            gastos.append(cuenta_obj)
            total_gastos += cuenta_obj['SaldoNeto']

    utilidad_bruta = total_ingresos - total_costos
    utilidad_neta = utilidad_bruta - total_gastos

    if request.args.get('print') == '1':
        return render_template('admin/estado_resultados_imprimir.html',
                               mes=mes, anio=anio,
                               ingresos=ingresos, total_ingresos=total_ingresos,
                               costos=costos, total_costos=total_costos,
                               gastos=gastos, total_gastos=total_gastos,
                               utilidad_bruta=utilidad_bruta,
                               utilidad_neta=utilidad_neta,
                               datetime=datetime)

    return render_template('admin/estado_resultados.html',
                           user=current_user,
                           mes=mes, anio=anio,
                           ingresos=ingresos, total_ingresos=total_ingresos,
                           costos=costos, total_costos=total_costos,
                           gastos=gastos, total_gastos=total_gastos,
                           utilidad_bruta=utilidad_bruta,
                           utilidad_neta=utilidad_neta)

# ============================================================
# NUEVAS RUTAS NIIF PROFESIONALES
# ============================================================

from app.services.contabilidad_service import ContabilidadService

@admin_bp.route('/contabilidad/catalogo', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def catalogo_cuentas():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cuentas = ContabilidadService.obtener_catalogo_cuentas(cursor)
        return render_template('admin/catalogo_cuentas.html', user=current_user, cuentas=cuentas)
    except Exception as e:
        flash(f'Error al cargar catálogo: {str(e)}', 'error')
        return redirect(url_for('admin.contabilidad'))
    finally:
        conn.close()

@admin_bp.route('/contabilidad/comprobacion', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def balance_comprobacion():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        mes = request.args.get('mes', datetime.now().month)
        anio = request.args.get('anio', datetime.now().year)

        balance=ContabilidadService.balanza_mensual(cursor,int(mes),int(anio))
        total_debe=sum(item['TotalDebe'] for item in balance)
        total_haber=sum(item['TotalHaber'] for item in balance)
        return render_template('admin/balance_comprobacion.html',
                               user=current_user,
                               balance=balance,
                               mes=mes, anio=anio,
                               total_debe=total_debe, total_haber=total_haber)
    except Exception as e:
        flash(f'Error al cargar balance: {str(e)}', 'error')
        return redirect(url_for('admin.contabilidad'))
    finally:
        conn.close()

@admin_bp.route('/contabilidad/mayor', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def libro_mayor():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cuenta_codigo = request.args.get('cuenta_codigo')
        mes = request.args.get('mes', datetime.now().month)
        anio = request.args.get('anio', datetime.now().year)

        cuentas = ContabilidadService.obtener_catalogo_cuentas(cursor, solo_transaccionales=True)

        movimientos = []
        if cuenta_codigo:
            cursor.execute("SELECT ID FROM PeriodosContables WHERE Mes = ? AND Anio = ?", (mes, anio))
            periodo_row = cursor.fetchone()
            if periodo_row:
                movimientos = ContabilidadService.obtener_libro_mayor(cursor, cuenta_codigo, periodo_id=periodo_row[0])

        return render_template('admin/libro_mayor.html',
                               user=current_user,
                               cuentas=cuentas,
                               movimientos=movimientos,
                               cuenta_seleccionada=cuenta_codigo,
                               mes=mes, anio=anio)
    except Exception as e:
        flash(f'Error al cargar libro mayor: {str(e)}', 'error')
        return redirect(url_for('admin.contabilidad'))
    finally:
        conn.close()

# ============================================================
# MÓDULO DE CONFIGURACIÓN
# ============================================================
