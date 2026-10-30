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


_NON_PRODUCIBLE_CATEGORIES = {'bebidas', 'bebida', 'reventa', 'productos de reventa'}


def _is_production_validation_error(exc: Exception) -> bool:
    msg = str(exc or '').lower()
    return any(
        token in msg
        for token in (
            '52031',
            '52032',
            '52033',
            '52034',
            '52035',
            '52036',
            'producto inactivo',
            'producto ficticio',
            'reventa',
            'bebidas',
            'sin receta',
            'tiene receta',
            'stock insuficiente',
        )
    )


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
        WHERE p.Activo = 1 AND ISNULL(p.EsFicticio, 0) = 0 AND c.Nombre NOT IN ('Bebidas', 'Bebida', 'Reventa')
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
    datos = request.json or {}
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
            'produccion.sp_ValidarProductoParaProduccion',
            (int(producto_id),),
            fallback_sql=(
                "SELECT p.ID, p.Nombre, p.Activo, ISNULL(p.EsFicticio, 0) AS EsFicticio, "
                "p.CategoriaID, c.Nombre AS CategoriaNombre, "
                "(SELECT COUNT(*) FROM RecetaProducto r WHERE r.ProductoID = p.ID) AS TieneReceta "
                "FROM Productos p WITH (UPDLOCK, HOLDLOCK) "
                "LEFT JOIN Categorias c ON c.ID = p.CategoriaID "
                "WHERE p.ID = ?"
            ),
        )
        prod_row = cursor.fetchone()
        if not prod_row:
            conn.rollback()
            return jsonify({'error': 'El producto especificado no existe.'}), 400

        prod_activo = bool(getattr(prod_row, 'Activo', prod_row[2] if len(prod_row) > 2 else 1))
        prod_ficticio = bool(getattr(prod_row, 'EsFicticio', prod_row[3] if len(prod_row) > 3 else 0))
        cat_nombre = str(getattr(prod_row, 'CategoriaNombre', prod_row[5] if len(prod_row) > 5 else '') or '').strip().lower()
        tiene_receta = int(getattr(prod_row, 'TieneReceta', prod_row[6] if len(prod_row) > 6 else 1) or 0)

        if not prod_activo:
            conn.rollback()
            return jsonify({'error': 'No se puede registrar producción para un producto inactivo.'}), 400
        if prod_ficticio:
            conn.rollback()
            return jsonify({'error': 'No se puede registrar producción para un producto ficticio o de servicio.'}), 400
        if cat_nombre in _NON_PRODUCIBLE_CATEGORIES:
            conn.rollback()
            return jsonify({'error': 'No se puede registrar producción para productos de reventa o bebidas.'}), 400
        if tiene_receta <= 0:
            conn.rollback()
            return jsonify({'error': 'El producto no tiene receta definida. Imposible producir sin receta.'}), 400

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
            conn.rollback()
            return jsonify({'error': 'El producto no tiene receta definida. Imposible producir sin receta.'}), 400

        for mat in materiales:
            if mat.StockActual < mat.Requerido:
                conn.rollback()
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
        return jsonify({'status': 'success', 'mensaje': f'Lote producido con éxito. Se crearon {cantidad} unidades.', 'id': lote_id})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        if _is_production_validation_error(e):
            return jsonify({'error': str(e)}), 400
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()
