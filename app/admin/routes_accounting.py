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
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE MONTH(FechaHora) = MONTH(GETDATE()) AND YEAR(FechaHora) = YEAR(GETDATE())")
    ingresos_mes = float(cursor.fetchone()[0])
    
    # 2. Compras de Materia Prima
    cursor.execute("SELECT ISNULL(SUM(CostoTotal), 0) FROM ComprasMateriaPrima WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    compras_mes = float(cursor.fetchone()[0])

    # 3. Egresos Privados
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM EgresosPrivados WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    egresos_mes = float(cursor.fetchone()[0])

    # Totales del DIA actual
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE CONVERT(date, FechaHora) = CONVERT(date, GETDATE())")
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
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_egreso():
    datos = request.json
    concepto = datos.get('concepto')
    monto = datos.get('monto')

    if not concepto or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO EgresosPrivados (Concepto, Monto, UsuarioID) OUTPUT INSERTED.EgresoID VALUES (?, ?, ?)",
            concepto, float(monto), current_user.id
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Egreso registrado', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/contabilidad/vales', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_vale():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    monto = datos.get('monto')

    if not empleado_id or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ValesEmpleados (EmpleadoID, Monto, FechaAlta) OUTPUT INSERTED.ValeID VALUES (?, ?, GETDATE())",
            int(empleado_id), float(monto)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Vale registrado', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/contabilidad/vales/<int:vale_id>/toggle', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_vale(vale_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 ^ Descontado WHERE ID = ?", vale_id)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado de vale actualizado'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

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
    
    # 1. Consulta con CTE para obtener Saldos Finales de Activo, Pasivo y Capital
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
        WHERE A.Estado = 'Contabilizado' 
          AND C.Clase IN ('Activo', 'Pasivo', 'Capital')
          AND A.Fecha <= ?
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
    data = request.json
    detalles = data.get('detalles', [])
    
    total_debe = sum(decimal.Decimal(str(d.get('debe', 0))) for d in detalles)
    total_haber = sum(decimal.Decimal(str(d.get('haber', 0))) for d in detalles)
    
    if total_debe != total_haber:
        return jsonify({'error': f'Descuadre: Debe ({total_debe}) != Haber ({total_haber})'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRAN")
        
        cursor.execute("""
            INSERT INTO AsientosDiario (PeriodoID, Descripcion, ReferenciaExterna, TipoDocumento, UsuarioID)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?)
        """, (data['periodo_id'], data['descripcion'], data.get('referencia'), 'Manual', current_user.ID))
        
        asiento_id = cursor.fetchone()[0]
        
        for d in detalles:
            cursor.execute("""
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber)
                VALUES (?, ?, ?, ?)
            """, (asiento_id, d['cuenta_id'], d.get('debe', 0), d.get('haber', 0)))
            
        cursor.execute("COMMIT")
        return jsonify({'success': True, 'asiento_id': asiento_id})
        
    except Exception as e:
        cursor.execute("ROLLBACK")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/contabilidad/cierre-periodo', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def cierre_periodo():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Aquí se ejecutaría el SP real de cierre contable en el futuro
        # cursor.execute("EXEC SP_CierreContablePeriodo @PeriodoID=?, @UsuarioID=?", ...)
        flash('El cierre contable aún no está implementado en la Base de Datos.', 'warning')
        return redirect(url_for('admin.balance_general'))
    except Exception as e:
        conn.rollback()
        flash(f'Error al procesar cierre: {str(e)}', 'error')
        return redirect(url_for('admin.balance_general'))
    finally:
        conn.close()

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
            C.Grupo,
            C.Codigo,
            C.Nombre AS Cuenta,
            C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM DetalleAsientos D
        JOIN AsientosDiario A ON D.AsientoID = A.ID
        JOIN CatalogoCuentas C ON D.CuentaID = C.ID
        WHERE A.Estado = 'Contabilizado' 
          AND C.Clase IN ('Ingreso', 'Costo', 'Gasto')
          AND A.PeriodoID = ?
        GROUP BY C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT 
        Grupo,
        Codigo,
        Cuenta,
        CASE 
            WHEN Naturaleza = 'Acreedora' THEN (TotalHaber - TotalDebe)
            ELSE (TotalDebe - TotalHaber) 
        END AS SaldoNeto
    FROM MovimientosResultados
    WHERE (TotalDebe - TotalHaber) != 0
    ORDER BY 
        CASE WHEN Grupo LIKE '%Ingreso%' THEN 1 
             WHEN Grupo LIKE '%Costo%' THEN 2 
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
        
        # Categorizar heurísticamente según el nombre del grupo
        grupo_lower = row.Grupo.lower()
        if 'ingreso' in grupo_lower or 'venta' in grupo_lower:
            ingresos.append(cuenta_obj)
            total_ingresos += cuenta_obj['SaldoNeto']
        elif 'costo' in grupo_lower:
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
# MÓDULO DE CONFIGURACIÓN
# ============================================================
