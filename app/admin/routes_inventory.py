# app/admin/routes_inventory.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

@admin_bp.route('/inventario')
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def inventario():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Materia Prima
    cursor.execute(
        "SELECT m.ID, m.Nombre, u.Nombre AS Unidad, m.StockActual, m.StockMinimo "
        "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY m.Nombre"
    )
    materias = [{'id': r.ID, 'nombre': r.Nombre, 'unidad': r.Unidad, 'stock': float(r.StockActual), 'minimo': float(r.StockMinimo)} for r in cursor.fetchall()]

    # Proveedores
    cursor.execute("SELECT ID, Nombre, Telefono FROM Proveedores WHERE Activo = 1 ORDER BY Nombre")
    proveedores = [{'id': r.ID, 'nombre': r.Nombre, 'telefono': r.Telefono or ''} for r in cursor.fetchall()]

    # Unidades de Medida
    cursor.execute("SELECT ID, Nombre, Abreviatura FROM UnidadesMedida ORDER BY Nombre")
    unidades = [{'id': r.ID, 'nombre': r.Nombre, 'abreviatura': r.Abreviatura} for r in cursor.fetchall()]

    # Historial de Compras (Últimas 50)
    cursor.execute(
        "SELECT TOP 50 c.ID, m.Nombre AS Materia, p.Nombre AS Proveedor, c.Cantidad, c.CostoTotal, c.Fecha "
        "FROM ComprasMateriaPrima c "
        "JOIN MateriaPrima m ON c.MateriaPrimaID = m.ID "
        "JOIN Proveedores p ON c.ProveedorID = p.ID "
        "ORDER BY c.Fecha DESC"
    )
    compras = [{'id': r.ID, 'materia': r.Materia, 'proveedor': r.Proveedor, 'cantidad': float(r.Cantidad), 'costo': float(r.CostoTotal), 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/inventario.html', user=current_user, materias=materias, proveedores=proveedores, unidades=unidades, compras=compras)



@admin_bp.route('/api/inventario/materia_prima', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_materia_prima():
    datos = request.json
    if not datos.get('nombre') or not datos.get('unidad_id') or not datos.get('stock_minimo'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO MateriaPrima (Nombre, UnidadMedidaID, StockMinimo, StockActual) OUTPUT INSERTED.MateriaPrimaID VALUES (?, ?, ?, 0.0)",
            datos.get('nombre'), int(datos.get('unidad_id')), float(datos.get('stock_minimo'))
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Materia prima creada con éxito', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/inventario/proveedor', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_proveedor():
    datos = request.json
    if not datos.get('nombre'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Proveedores (Nombre, Telefono) OUTPUT INSERTED.ID VALUES (?, ?)",
            datos.get('nombre'), datos.get('telefono', '')
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Proveedor creado con éxito', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/inventario/compra', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def registrar_compra():
    datos = request.json
    if not all([datos.get('materia_id'), datos.get('proveedor_id'), datos.get('cantidad'), datos.get('costo')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Registrar compra
        cursor.execute(
            "INSERT INTO ComprasMateriaPrima (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal) OUTPUT INSERTED.ID VALUES (?, ?, ?, ?)",
            int(datos.get('materia_id')), int(datos.get('proveedor_id')), float(datos.get('cantidad')), float(datos.get('costo'))
        )
        new_id = cursor.fetchone()[0]
        # Sumar stock
        cursor.execute(
            "UPDATE MateriaPrima SET StockActual = StockActual + ? WHERE ID = ?",
            float(datos.get('cantidad')), int(datos.get('materia_id'))
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Compra registrada y stock actualizado', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


# ============================================================
# MÓDULO DE PRODUCCIÓN Y RECETAS
# ============================================================


