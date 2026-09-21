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
# MÓDULO DE CONFIGURACIÓN
# ============================================================


