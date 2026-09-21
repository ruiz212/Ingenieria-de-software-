# app/admin/routes_catalog.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

@admin_bp.route('/catalogo')
@login_required
@roles_required('Admin', 'SuperAdmin')
def catalogo():
    """Gestor de Catálogo y Precios."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener categorías
    cursor.execute("SELECT ID, Nombre FROM Categorias ORDER BY Nombre")
    categorias = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    # Obtener productos
    cursor.execute(
        "SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.CategoriaID, p.PrecioBase, p.Activo, p.EsFicticio, p.PorcentajeDescuento "
        "FROM Productos p "
        "JOIN Categorias c ON p.CategoriaID = c.ID "
        "ORDER BY c.Nombre, p.Nombre"
    )
    productos = [
        {'id': row.ID, 'nombre': row.Nombre, 'categoria': row.Categoria, 'categoria_id': row.CategoriaID,
         'precio': float(row.PrecioBase), 'activo': bool(row.Activo), 
         'es_ficticio': bool(row.EsFicticio), 'descuento': float(row.PorcentajeDescuento)}
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template('admin/catalogo.html', user=current_user, productos=productos, categorias=categorias)



@admin_bp.route('/api/productos', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_producto():
    """API para crear un nuevo producto."""
    datos = request.json
    nombre = datos.get('nombre')
    precio = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento = datos.get('descuento', 0.0)

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Productos (Nombre, PrecioBase, CategoriaID, EsFicticio, Activo, PorcentajeDescuento) "
            "OUTPUT INSERTED.ProductoID VALUES (?, ?, ?, 0, 1, ?)",
            nombre, float(precio), int(categoria_id), float(descuento)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Producto creado con éxito', 'id': new_id})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/productos/<int:producto_id>/toggle', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_producto(producto_id):
    """API para activar/desactivar un producto."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Productos SET Activo = 1 ^ Activo WHERE ID = ?", producto_id
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado actualizado'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/productos/<int:producto_id>/editar', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def editar_producto(producto_id):
    """API para editar un producto existente."""
    datos = request.json
    nombre = datos.get('nombre')
    precio = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento = datos.get('descuento', 0.0)

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Productos SET Nombre = ?, PrecioBase = ?, CategoriaID = ?, PorcentajeDescuento = ? WHERE ID = ?",
            nombre, float(precio), int(categoria_id), float(descuento), producto_id
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Producto actualizado con éxito'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


