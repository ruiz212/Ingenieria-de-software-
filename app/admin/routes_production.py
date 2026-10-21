from app.services.validation import amount, positive_int
# app/admin/routes_production.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime


@admin_bp.route('/produccion')
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def produccion():
    conn = get_db_connection()
    cursor = conn.cursor()

    execute_sp(
        cursor,
        'catalogo.sp_ObtenerProductosParaProduccion',
        fallback_sql="""
        SELECT p.ID, p.Nombre 
        FROM Productos p
        JOIN Categorias c ON p.CategoriaID = c.ID
        WHERE p.Activo = 1 AND c.Nombre != 'Bebidas'
        ORDER BY p.Nombre
    """,
    )
    productos = [{'id': r.ID, 'nombre': r.Nombre} for r in cursor.fetchall()]

    execute_sp(
        cursor,
        'produccion.sp_ObtenerMateriasPrimasConUnidad',
        fallback_sql=(
            "SELECT m.ID, m.Nombre, u.Abreviatura "
            "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
            "ORDER BY m.Nombre"
        ),
    )
    materias = [{'id': r.ID, 'nombre': f"{r.Nombre} ({r.Abreviatura})"} for r in cursor.fetchall()]

    # Recetas agrupadas por producto mediante SP
    execute_sp(
        cursor,
        'produccion.sp_ListarProduccionYRecetas',
        fallback_sql=(
            "SELECT r.ID, p.Nombre AS Producto, m.Nombre AS Materia, r.CantidadNecesaria, u.Abreviatura "
            "FROM RecetaProducto r "
            "JOIN Productos p ON r.ProductoID = p.ID "
            "JOIN MateriaPrima m ON r.MateriaPrimaID = m.ID "
            "JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
            "ORDER BY p.Nombre, m.Nombre"
        ),
    )
    recetas_raw = cursor.fetchall()
    recetas_agrupadas = {}
    for r in recetas_raw:
        if r.Producto not in recetas_agrupadas:
            recetas_agrupadas[r.Producto] = []
        recetas_agrupadas[r.Producto].append({'id': r.ID, 'materia': r.Materia, 'cantidad': float(r.CantidadNecesaria), 'abreviatura': r.Abreviatura})

    execute_sp(
        cursor,
        'produccion.sp_ListarUltimosLotesProduccion',
        fallback_sql=(
            "SELECT TOP 50 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.Fecha "
            "FROM ProduccionLotes pl "
            "JOIN Productos p ON pl.ProductoID = p.ID "
            "ORDER BY pl.Fecha DESC"
        ),
    )
    lotes = [{'id': r.ID, 'producto': r.Producto, 'cantidad': r.CantidadProducida, 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/produccion.html', user=current_user, productos=productos, materias=materias, recetas_agrupadas=recetas_agrupadas, lotes=lotes)


@admin_bp.route('/api/produccion/receta', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_receta():
    datos = request.json
    if not all([datos.get('producto_id'), datos.get('materia_id'), datos.get('cantidad')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cantidad_nec = amount(datos.get('cantidad'), 'Cantidad', minimum=0.01)
        execute_sp(
            cursor,
            'produccion.sp_GuardarRecetaProducto',
            (int(datos.get('producto_id')), int(datos.get('materia_id')), cantidad_nec),
            fallback_sql=(
                "INSERT INTO RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria) VALUES (?, ?, ?)"
            ),
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Receta actualizada con éxito'})
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


@admin_bp.route('/api/produccion/receta/<int:receta_id>/delete', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def eliminar_receta(receta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_EliminarRecetaProducto',
            (receta_id,),
            fallback_sql="DELETE FROM RecetaProducto WHERE ID = ?",
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Ingrediente removido de la receta'})
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


@admin_bp.route('/api/produccion/lote', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def registrar_lote():
    datos = request.json
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad')

    if not producto_id or not cantidad or int(cantidad) <= 0:
        return jsonify({'error': 'Datos inválidos'}), 400

    cantidad = positive_int(cantidad)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_ObtenerMaterialesRequeridosLote',
            (cantidad, int(producto_id)),
            fallback_sql="""
            SELECT m.ID, m.Nombre, m.StockActual, (r.CantidadNecesaria * ?) AS Requerido
            FROM RecetaProducto r
            JOIN MateriaPrima m WITH (UPDLOCK,HOLDLOCK) ON r.MateriaPrimaID = m.ID
            WHERE r.ProductoID = ?
        """,
        )

        materiales = cursor.fetchall()

        if not materiales:
            return jsonify({'error': 'El producto no tiene receta definida. Imposible producir sin receta.'}), 400

        for mat in materiales:
            if mat.StockActual < mat.Requerido:
                return jsonify({'error': f'Stock insuficiente de {mat.Nombre}. Se requieren {mat.Requerido} y hay {mat.StockActual}.'}), 400

        execute_sp(
            cursor,
            'produccion.sp_InsertarLoteProduccion',
            (int(producto_id), cantidad),
            fallback_sql="INSERT INTO ProduccionLotes (ProductoID, CantidadProducida) OUTPUT INSERTED.ID VALUES (?, ?)",
        )
        lote_id = cursor.fetchone().ID

        for mat in materiales:
            execute_sp(
                cursor,
                'produccion.sp_DescontarStockMateriaPrimaLote',
                (mat.Requerido, mat.ID, mat.Requerido),
                fallback_sql="UPDATE MateriaPrima SET StockActual = StockActual - ? WHERE ID = ? AND StockActual >= ?",
            )
            if cursor.rowcount != 1:
                raise ValueError("Stock insuficiente; actualice la página.")
            execute_sp(
                cursor,
                'produccion.sp_InsertarConsumoLote',
                (lote_id, mat.ID, mat.Requerido),
                fallback_sql="INSERT INTO ConsumoLote (LoteID, MateriaPrimaID, CantidadUsada) VALUES (?, ?, ?)",
            )

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Lote producido con éxito. Se crearon {cantidad} unidades.'})
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
