# app/admin/routes_production.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

@admin_bp.route('/produccion')
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def produccion():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Productos (Excluir Bebidas y otras categorías que solo se revenden, asumiendo CategoriaID != 4 si 4 es Bebidas)
    # Mejor aún, uniremos con Categorias para excluir explícitamente 'Bebidas'
    cursor.execute("""
        SELECT p.ID, p.Nombre 
        FROM Productos p
        JOIN Categorias c ON p.CategoriaID = c.ID
        WHERE p.Activo = 1 AND c.Nombre != 'Bebidas'
        ORDER BY p.Nombre
    """)
    productos = [{'id': r.ID, 'nombre': r.Nombre} for r in cursor.fetchall()]

    # Materias Primas para agregar a receta
    cursor.execute(
        "SELECT m.ID, m.Nombre, u.Abreviatura "
        "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY m.Nombre"
    )
    materias = [{'id': r.ID, 'nombre': f"{r.Nombre} ({r.Abreviatura})" } for r in cursor.fetchall()]

    # Recetas agrupadadas por producto
    cursor.execute(
        "SELECT r.ID, p.Nombre AS Producto, m.Nombre AS Materia, r.CantidadNecesaria, u.Abreviatura "
        "FROM RecetaProducto r "
        "JOIN Productos p ON r.ProductoID = p.ID "
        "JOIN MateriaPrima m ON r.MateriaPrimaID = m.ID "
        "JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY p.Nombre, m.Nombre"
    )
    recetas_raw = cursor.fetchall()
    recetas_agrupadas = {}
    for r in recetas_raw:
        if r.Producto not in recetas_agrupadas:
            recetas_agrupadas[r.Producto] = []
        recetas_agrupadas[r.Producto].append({'id': r.ID, 'materia': r.Materia, 'cantidad': float(r.CantidadNecesaria), 'abreviatura': r.Abreviatura})

    # Historial de Producción (Últimos 50 lotes)
    cursor.execute(
        "SELECT TOP 50 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.Fecha "
        "FROM ProduccionLotes pl "
        "JOIN Productos p ON pl.ProductoID = p.ID "
        "ORDER BY pl.Fecha DESC"
    )
    lotes = [{'id': r.ID, 'producto': r.Producto, 'cantidad': r.CantidadProducida, 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/produccion.html', user=current_user, productos=productos, materias=materias, recetas_agrupadas=recetas_agrupadas, lotes=lotes)



@admin_bp.route('/api/produccion/receta', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_receta():
    datos = request.json
    if not all([datos.get('producto_id'), datos.get('materia_id'), datos.get('cantidad')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verificar si ya existe para actualizar o insertar
        cursor.execute("SELECT ID FROM RecetaProducto WHERE ProductoID = ? AND MateriaPrimaID = ?", int(datos.get('producto_id')), int(datos.get('materia_id')))
        existente = cursor.fetchone()
        
        if existente:
            cursor.execute("UPDATE RecetaProducto SET CantidadNecesaria = ? WHERE ID = ?", float(datos.get('cantidad')), existente.ID)
        else:
            cursor.execute(
                "INSERT INTO RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria) VALUES (?, ?, ?)",
                int(datos.get('producto_id')), int(datos.get('materia_id')), float(datos.get('cantidad'))
            )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Receta actualizada con éxito'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/produccion/receta/<int:receta_id>/delete', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def eliminar_receta(receta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM RecetaProducto WHERE ID = ?", receta_id)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Ingrediente removido de la receta'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/produccion/lote', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def registrar_lote():
    datos = request.json
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad')
    
    if not producto_id or not cantidad or int(cantidad) <= 0:
        return jsonify({'error': 'Datos inválidos'}), 400
        
    cantidad = int(cantidad)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Obtener receta y verificar stock en un solo JOIN (Prevenir N+1)
        cursor.execute("""
            SELECT m.ID, m.Nombre, m.StockActual, (r.CantidadNecesaria * ?) AS Requerido
            FROM RecetaProducto r
            JOIN MateriaPrima m ON r.MateriaPrimaID = m.ID
            WHERE r.ProductoID = ?
        """, cantidad, int(producto_id))
        
        materiales = cursor.fetchall()
        
        if not materiales:
            return jsonify({'error': 'El producto no tiene receta definida. Imposible producir sin receta.'}), 400
            
        # Verificar stock de todos los materiales (Capa aplicación, antes del INSERT)
        for mat in materiales:
            if mat.StockActual < mat.Requerido:
                return jsonify({'error': f'Stock insuficiente de {mat.Nombre}. Se requieren {mat.Requerido} y hay {mat.StockActual}.'}), 400
                
        # Todo bien, insertar lote
        cursor.execute("INSERT INTO ProduccionLotes (ProductoID, CantidadProducida) OUTPUT INSERTED.ID VALUES (?, ?)", int(producto_id), cantidad)
        lote_id = cursor.fetchone().ID
        
        # Descontar stock e insertar consumo (Si hay race condition y StockActual queda en negativo, el CHECK constraint abortará la transacción)
        for mat in materiales:
            cursor.execute("UPDATE MateriaPrima SET StockActual = StockActual - ? WHERE ID = ?", mat.Requerido, mat.ID)
            cursor.execute("INSERT INTO ConsumoLote (LoteID, MateriaPrimaID, CantidadUsada) VALUES (?, ?, ?)", lote_id, mat.ID, mat.Requerido)
            
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Lote producido con éxito. Se crearon {cantidad} unidades.'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE FIDELIZACIÓN (CRM)
# ============================================================


