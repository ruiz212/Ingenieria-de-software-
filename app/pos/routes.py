# app/pos/routes.py
# Rutas del Punto de Venta y API de Facturas

import uuid
import os
from datetime import datetime

from flask import render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user

from app.pos import pos_bp
from app.db import get_db_connection, obtener_o_crear_turno
from app.extensions import csrf
from app.utils.qr import generar_qr_base64
from app.auth.decorators import roles_required


@pos_bp.route('/pos')
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Cliente', 'Invitado')
def index():
    """Carga productos, categorías e ingredientes desde la BD."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener categorías activas
    cursor.execute("SELECT ID, Nombre FROM Categorias ORDER BY Nombre")
    categorias = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    # Obtener productos activos con su categoría
    cursor.execute(
        "SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.PrecioBase, p.EsFicticio, p.PorcentajeDescuento "
        "FROM Productos p "
        "JOIN Categorias c ON p.CategoriaID = c.ID "
        "WHERE p.Activo = 1 "
        "ORDER BY c.Nombre, p.Nombre"
    )
    productos = [
        {'id': row.ID, 'nombre': row.Nombre, 'categoria': row.Categoria,
         'precio': float(row.PrecioBase), 'es_ficticio': row.EsFicticio, 'descuento': float(row.PorcentajeDescuento)}
        for row in cursor.fetchall()
    ]

    # Obtener ingredientes extras activos
    cursor.execute(
        "SELECT ID, Nombre, PrecioAdicional FROM Ingredientes WHERE Activo = 1 ORDER BY Nombre"
    )
    ingredientes = [
        {'id': row.ID, 'nombre': row.Nombre, 'precio': float(row.PrecioAdicional)}
        for row in cursor.fetchall()
    ]

    conn.close()

    return render_template('index.html',
                           productos=productos,
                           ingredientes=ingredientes,
                           categorias=categorias,
                           user=current_user,
                           mes_actual=datetime.now().month)

@pos_bp.route('/api/upload_referencia', methods=['POST'])
@csrf.exempt
@login_required
def upload_referencia():
    if 'foto' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['foto']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'referencias')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        return jsonify({'ruta': f"uploads/referencias/{unique_filename}"}), 200


@pos_bp.route('/api/factura', methods=['POST'])
@csrf.exempt
@login_required
def registrar_factura():
    """Registra una factura completa en la BD con sus detalles, pagos y encargos."""
    datos = request.json
    carrito = datos.get('carrito', [])
    total = datos.get('total', 0)
    subtotal = datos.get('subtotal', 0)
    iva = datos.get('iva', 0)
    es_encargo = datos.get('es_encargo', False)
    datos_encargo = datos.get('encargo_detalles', None)
    metodo_pago = datos.get('metodo_pago', 'Efectivo')
    nombre_transferente = datos.get('nombre_transferente', None)

    if not carrito or total <= 0:
        return jsonify({'error': 'El carrito está vacío o el total es inválido'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Obtener o crear turno activo (solo para empleados)
        es_cliente_registrado = getattr(current_user, 'rol_nombre', '') == 'Cliente'
        es_invitado = getattr(current_user, 'rol_nombre', '') == 'Invitado'
        
        turno_id = None
        if not (es_cliente_registrado or es_invitado):
            turno_id = obtener_o_crear_turno(current_user.id)
        # 2. Generar número de factura correlativo desde la BD
        cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM Facturas")
        siguiente_num = cursor.fetchone()[0]
        numero_factura = f"FAC-{siguiente_num:04d}"
        codigo_seguimiento = uuid.uuid4().hex[:8].upper()

        # 3. Determinar ClienteID y guardar datos del cliente si es encargo
        cliente_id = 1 # Cliente General por defecto
        telefono_contacto_encargo = None
        es_cliente_registrado = getattr(current_user, 'rol_nombre', '') == 'Cliente'
        
        if es_cliente_registrado:
            cliente_id = current_user.id
        elif es_encargo and datos_encargo:
            nombre_cli = datos_encargo.get('nombre_cliente', '').strip()
            telefono_cli = datos_encargo.get('telefono', '').strip()
            telefono_contacto_encargo = telefono_cli if telefono_cli else None
            
            if nombre_cli:
                # Intentar buscar el cliente por telefono
                if telefono_cli:
                    cursor.execute("SELECT ID FROM Clientes WHERE Telefono = ?", telefono_cli)
                    row_cli = cursor.fetchone()
                    if row_cli:
                        cliente_id = row_cli.ID
                    else:
                        cursor.execute("INSERT INTO Clientes (Nombre, Telefono, NivelConfianzaID) OUTPUT INSERTED.ID VALUES (?, ?, 1)", nombre_cli, telefono_cli)
                        cliente_id = cursor.fetchone()[0]
                else:
                    # Crear nuevo cliente si no hay telefono para buscar
                    cursor.execute("INSERT INTO Clientes (Nombre, Telefono, NivelConfianzaID) OUTPUT INSERTED.ID VALUES (?, NULL, 1)", nombre_cli)
                    cliente_id = cursor.fetchone()[0]

        # 4. Insertar la factura
        cursor.execute(
            "INSERT INTO Facturas (NumeroFactura, CodigoSeguimiento, UsuarioID, ClienteID, TurnoID, Subtotal, IVA, Total, EsEncargo) "
            "OUTPUT INSERTED.ID "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            numero_factura, codigo_seguimiento, current_user.id, cliente_id, turno_id,
            subtotal, iva, total, 1 if es_encargo else 0
        )
        factura_id = cursor.fetchone()[0]

        # 4. Insertar detalle de cada producto
        for item in carrito:
            # item['id'] puede venir como "3_16278839" si tiene ingredientes. Extraemos el ID real (el primer elemento).
            prod_id_str = str(item.get('id', '1'))
            prod_id = int(prod_id_str.split('_')[0])

            cursor.execute(
                "INSERT INTO DetalleFacturas (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal) "
                "OUTPUT INSERTED.ID "
                "VALUES (?, ?, ?, ?, ?)",
                factura_id, prod_id, item.get('cantidad', 1),
                item.get('precio', 0), item.get('subtotal', 0)
            )
            detalle_id = cursor.fetchone()[0]

            # 4b. Insertar ingredientes extra si los tiene
            extras = item.get('detalle_ingredientes')
            if extras and isinstance(extras, dict) and 'ingredientes' in extras:
                for extra in extras['ingredientes']:
                    # El extra ahora no tiene ID en pos.js (solo nombre y precio), 
                    # pero la tabla DetalleIngredientes necesita un IngredienteID.
                    # Buscamos el ID por nombre o usamos un genérico.
                    cursor.execute("SELECT ID FROM Ingredientes WHERE Nombre = ?", extra.get('nombre', ''))
                    ing_row = cursor.fetchone()
                    ing_id = ing_row.ID if ing_row else 1 # Fallback al primer ingrediente si no se encuentra
                    
                    cursor.execute(
                        "INSERT INTO DetalleIngredientes (DetalleFacturaID, IngredienteID, PrecioAplicado) "
                        "VALUES (?, ?, ?)",
                        detalle_id, ing_id, extra.get('precio', 0)
                    )

        # 5. Registrar el pago (soporta pago dividido 50/50)
        if es_encargo and datos_encargo:
            adelanto = datos_encargo.get('adelanto', 0)
            metodo_adelanto = datos_encargo.get('metodo_adelanto', 'Efectivo')

            # Pago del adelanto
            if adelanto > 0:
                cursor.execute(
                    "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente) VALUES (?, ?, ?, ?)",
                    factura_id, metodo_adelanto, adelanto,
                    nombre_transferente if metodo_adelanto == 'Transferencia' else None
                )

            # Registrar encargo
            fecha_entrega = datos_encargo.get('fecha_entrega', datetime.now().strftime('%Y-%m-%d'))
            especificaciones = datos_encargo.get('especificaciones', None)
            ruta_imagen = datos_encargo.get('ruta_imagen_referencia', None)
            
            cursor.execute(
                "INSERT INTO Encargos (FacturaID, FechaEntrega, Estado, NotasCliente, Especificaciones, RutaImagenReferencia, TelefonoContacto) VALUES (?, ?, 'Pendiente', ?, ?, ?, ?)",
                factura_id, fecha_entrega, datos_encargo.get('notas', ''), especificaciones, ruta_imagen, telefono_contacto_encargo
            )
        else:
            # Venta de mostrador: pago completo
            cursor.execute(
                "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente) VALUES (?, ?, ?, ?)",
                factura_id, metodo_pago, total,
                nombre_transferente if metodo_pago == 'Transferencia' else None
            )

        conn.commit()

        # 6. Generar QR de seguimiento
        base_url = request.host_url.rstrip('/')
        url_seguimiento = f"{base_url}/seguimiento/{codigo_seguimiento}"
        qr_base64 = generar_qr_base64(url_seguimiento)

        fecha_actual = datetime.now()
        factura_data = {
            'numero_factura': numero_factura,
            'codigo_seguimiento': codigo_seguimiento,
            'fecha': fecha_actual.strftime('%d/%m/%Y'),
            'hora': fecha_actual.strftime('%H:%M:%S'),
            'productos': carrito,
            'subtotal': subtotal,
            'iva': iva,
            'total': total,
            'es_encargo': es_encargo,
            'encargo_detalles': datos_encargo,
            'qr_image': qr_base64,
            'url_seguimiento': url_seguimiento
        }

        return jsonify({
            'status': 'success',
            'mensaje': 'Factura registrada con éxito',
            'factura': factura_data
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Error al registrar factura: {str(e)}'}), 500
    finally:
        conn.close()

# ============================================================
# API DE COTIZACIONES DE PASTELES PERSONALIZADOS
# ============================================================

from flask import session

@pos_bp.route('/api/cotizaciones', methods=['POST'])
@csrf.exempt
@login_required
def crear_cotizacion():
    datos = request.json
    especificaciones = datos.get('especificaciones')
    fecha_entrega = datos.get('fecha_entrega')
    ruta_imagen = datos.get('ruta_imagen_referencia')
    telefono = datos.get('telefono')

    if not especificaciones or not fecha_entrega:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cliente_id = current_user.id if current_user.rol_nombre in ['Cliente', 'Invitado'] and not current_user.es_invitado else None
    
    # Para invitados, usamos un Session ID
    session_id = None
    if not cliente_id:
        if 'cotizacion_session_id' not in session:
            import uuid
            session['cotizacion_session_id'] = str(uuid.uuid4())
        session_id = session['cotizacion_session_id']
        
    try:
        cursor.execute(
            "INSERT INTO Cotizaciones (ClienteID, SessionID, Especificaciones, FechaEntrega, RutaImagenReferencia, TelefonoContacto, Estado) "
            "VALUES (?, ?, ?, ?, ?, ?, 'Pendiente')",
            cliente_id, session_id, especificaciones, fecha_entrega, ruta_imagen, telefono
        )
        conn.commit()
        return jsonify({'mensaje': 'Cotización solicitada correctamente'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@pos_bp.route('/api/cotizaciones/cliente', methods=['GET'])
@login_required
def obtener_cotizaciones_cliente():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cliente_id = current_user.id if current_user.rol_nombre in ['Cliente', 'Invitado'] and not current_user.es_invitado else None
    session_id = session.get('cotizacion_session_id')
    
    if cliente_id:
        cursor.execute("SELECT * FROM Cotizaciones WHERE ClienteID = ? ORDER BY FechaSolicitud DESC", cliente_id)
    elif session_id:
        cursor.execute("SELECT * FROM Cotizaciones WHERE SessionID = ? ORDER BY FechaSolicitud DESC", session_id)
    else:
        return jsonify([])
        
    cotizaciones = []
    for row in cursor.fetchall():
        cotizaciones.append({
            'id': row.ID,
            'especificaciones': row.Especificaciones,
            'fecha_entrega': row.FechaEntrega.strftime('%Y-%m-%d') if row.FechaEntrega else '',
            'ruta_imagen': row.RutaImagenReferencia,
            'estado': row.Estado,
            'precio_cotizado': float(row.PrecioCotizado) if row.PrecioCotizado else None
        })
    
    conn.close()
    return jsonify(cotizaciones)

@pos_bp.route('/api/cotizaciones/pendientes', methods=['GET'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def obtener_cotizaciones_pendientes():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*, cl.Nombre AS ClienteNombre 
        FROM Cotizaciones c
        LEFT JOIN Clientes cl ON c.ClienteID = cl.ID
        WHERE c.Estado = 'Pendiente'
        ORDER BY c.FechaSolicitud ASC
    """)
    
    cotizaciones = []
    for row in cursor.fetchall():
        cotizaciones.append({
            'id': row.ID,
            'cliente': row.ClienteNombre or 'Invitado',
            'telefono': row.TelefonoContacto,
            'especificaciones': row.Especificaciones,
            'fecha_entrega': row.FechaEntrega.strftime('%Y-%m-%d') if row.FechaEntrega else '',
            'ruta_imagen': row.RutaImagenReferencia,
            'fecha_solicitud': row.FechaSolicitud.strftime('%Y-%m-%d %H:%M')
        })
        
    conn.close()
    return jsonify(cotizaciones)

@pos_bp.route('/api/cotizaciones/<int:id>/cotizar', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def cotizar_pedido(id):
    datos = request.json
    precio = datos.get('precio')
    
    if not precio:
        return jsonify({'error': 'Precio es requerido'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "UPDATE Cotizaciones SET PrecioCotizado = ?, Estado = 'Cotizada' WHERE ID = ?",
            precio, id
        )
        conn.commit()
        return jsonify({'mensaje': 'Cotización enviada'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@pos_bp.route('/api/cotizaciones/<int:id>/rechazar', methods=['POST'])
@csrf.exempt
@login_required
def rechazar_cotizacion(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE Cotizaciones SET Estado = 'Rechazada' WHERE ID = ?", id)
        conn.commit()
        return jsonify({'mensaje': 'Cotización rechazada'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
