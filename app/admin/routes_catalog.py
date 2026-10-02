# app/admin/routes_catalog.py
import os
import base64
import logging
import traceback
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf


# ── Mapa de emojis/defaults por categoría (fallback sin imagen) ──────────────
CATEGORY_DEFAULT_EMOJI = {
    'pan dulce':      '🍞',
    'pan salado':     '🥖',
    'reposteria':     '🎂',
    'repostería':     '🎂',
    'galletas':       '🍪',
    'bebidas':        '☕',
    'postres frios':  '🍰',
    'postres fríos':  '🍰',
}


# ─────────────────────────────────────────────────────────────────────────────
# VISTA — Catálogo
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/catalogo')
@login_required
@roles_required('Admin', 'SuperAdmin')
def catalogo():
    """Gestor de Catálogo y Precios."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT ID, Nombre FROM Categorias ORDER BY Nombre")
    categorias = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    cursor.execute(
        "SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.CategoriaID, "
        "p.PrecioBase, p.Activo, p.EsFicticio, p.PorcentajeDescuento, p.ImagenUrl "
        "FROM Productos p "
        "JOIN Categorias c ON p.CategoriaID = c.ID "
        "ORDER BY c.Nombre, p.Nombre"
    )
    productos = [
        {
            'id': row.ID,
            'nombre': row.Nombre,
            'categoria': row.Categoria,
            'categoria_id': row.CategoriaID,
            'precio': float(row.PrecioBase),
            'activo': bool(row.Activo),
            'es_ficticio': bool(row.EsFicticio),
            'descuento': float(row.PorcentajeDescuento),
            'imagen_url': row.ImagenUrl or '',
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template(
        'admin/catalogo.html',
        user=current_user,
        productos=productos,
        categorias=categorias,
    )


# ─────────────────────────────────────────────────────────────────────────────
# API — Subir imagen de producto a ImgBB
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/api/productos/upload_imagen', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def upload_imagen_producto():
    """Sube una imagen a ImgBB y devuelve la URL pública."""
    if 'imagen' not in request.files:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400

    file = request.files['imagen']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400

    # Validar tipo de archivo
    allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'error': f'Formato no permitido. Use: {", ".join(allowed_ext)}'}), 400

    # Validar tamaño (máx 5 MB)
    file.seek(0, 2)
    size_bytes = file.tell()
    file.seek(0)
    if size_bytes > 5 * 1024 * 1024:
        return jsonify({'error': 'La imagen no puede superar los 5 MB'}), 400

    api_key = os.environ.get('IMGBB_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'IMGBB_API_KEY no está configurado en el servidor'}), 500

    try:
        import requests as req
        img_data = file.read()
        b64_image = base64.b64encode(img_data).decode('utf-8')

        response = req.post(
            'https://api.imgbb.com/1/upload',
            data={
                'key': api_key,
                'image': b64_image,
                'name': f"producto_{file.filename}",
            },
            timeout=15
        )
        result = response.json()
        if result.get('success'):
            url = result['data']['url']
            return jsonify({'status': 'success', 'url': url})
        else:
            msg = result.get('error', {}).get('message', 'Error desconocido en ImgBB')
            return jsonify({'error': f'ImgBB: {msg}'}), 500

    except Exception as e:
        logging.error(f"upload_imagen_producto error: {e}")
        return jsonify({'error': f'Error de conexión: {str(e)}'}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — Crear producto
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/api/productos', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_producto():
    """API para crear un nuevo producto."""
    datos = request.json
    nombre      = datos.get('nombre', '').strip()
    precio      = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento   = datos.get('descuento', 0.0)
    imagen_url  = datos.get('imagen_url', '') or None   # None → columna queda NULL

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Productos "
            "(Nombre, PrecioBase, CategoriaID, EsFicticio, Activo, PorcentajeDescuento, ImagenUrl) "
            "OUTPUT INSERTED.ID "
            "VALUES (?, ?, ?, 0, 1, ?, ?)",
            nombre, float(precio), int(categoria_id), float(descuento), imagen_url
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Producto creado con éxito',
            'id': new_id,
            'imagen_url': imagen_url or '',
        })
    except Exception as e:
        conn.rollback()
        logging.error(f"crear_producto error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# API — Toggle activo/inactivo
# ─────────────────────────────────────────────────────────────────────────────
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
        logging.error(f"toggle_producto error: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# API — Editar producto
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/api/productos/<int:producto_id>/editar', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def editar_producto(producto_id):
    """API para editar un producto existente."""
    datos = request.json
    nombre      = datos.get('nombre', '').strip()
    precio      = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento   = datos.get('descuento', 0.0)
    imagen_url  = datos.get('imagen_url')   # puede venir None o string vacío

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    # Si imagen_url es string vacío, lo ponemos None para guardar NULL;
    # si viene None es que el usuario no tocó la imagen → conservar la actual
    actualizar_imagen = 'imagen_url' in datos
    imagen_value = (imagen_url or None) if actualizar_imagen else '_SKIP_'

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if actualizar_imagen:
            cursor.execute(
                "UPDATE Productos "
                "SET Nombre = ?, PrecioBase = ?, CategoriaID = ?, "
                "PorcentajeDescuento = ?, ImagenUrl = ? "
                "WHERE ID = ?",
                nombre, float(precio), int(categoria_id),
                float(descuento), imagen_value, producto_id
            )
        else:
            cursor.execute(
                "UPDATE Productos "
                "SET Nombre = ?, PrecioBase = ?, CategoriaID = ?, PorcentajeDescuento = ? "
                "WHERE ID = ?",
                nombre, float(precio), int(categoria_id), float(descuento), producto_id
            )
        conn.commit()

        # Obtener imagen_url actual para devolverla
        cursor.execute("SELECT ImagenUrl FROM Productos WHERE ID = ?", producto_id)
        row = cursor.fetchone()
        img = row.ImagenUrl if row else ''

        return jsonify({
            'status': 'success',
            'mensaje': 'Producto actualizado con éxito',
            'imagen_url': img or '',
        })
    except Exception as e:
        conn.rollback()
        logging.error(f"editar_producto error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()
