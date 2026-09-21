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

    # Obtener categorías activas que tengan al menos un producto activo
    cursor.execute("""
        SELECT DISTINCT c.ID, c.Nombre 
        FROM Categorias c
        JOIN Productos p ON p.CategoriaID = c.ID
        WHERE p.Activo = 1
        ORDER BY c.Nombre
    """)
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

    # Obtener configuración del sistema (IVA, etc)
    cursor.execute("SELECT Clave, Valor FROM ConfiguracionSistema")
    configuracion = {row.Clave: row.Valor for row in cursor.fetchall()}

    conn.close()

    es_cliente = getattr(current_user, 'rol_nombre', '') in ['Cliente', 'Invitado']
    template = 'tienda.html' if es_cliente else 'pos.html'

    return render_template(template,
                           productos=productos,
                           ingredientes=ingredientes,
                           categorias=categorias,
                           configuracion=configuracion,
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
        import requests
        import base64
        import os
        
        # Lee la imagen y la codifica en base64
        img_data = file.read()
        b64_image = base64.b64encode(img_data).decode('utf-8')
        
        # API Key de ImgBB (debe configurarse en .env, si no usa una por defecto o falla)
        # Nota: Por favor define IMGBB_API_KEY en tu archivo .env
        api_key = os.environ.get('IMGBB_API_KEY', '')
        
        if not api_key:
            return jsonify({'error': 'La clave de API de ImgBB no está configurada (IMGBB_API_KEY).'}), 500

        try:
            # Petición a la API de ImgBB
            response = requests.post(
                'https://api.imgbb.com/1/upload',
                data={
                    'key': api_key,
                    'image': b64_image
                }
            )
            
            result = response.json()
            if result.get('success'):
                url_imagen = result['data']['url']
                return jsonify({'ruta': url_imagen}), 200
            else:
                error_msg = result.get('error', {}).get('message', 'Error desconocido en ImgBB')
                return jsonify({'error': f'Error al subir a ImgBB: {error_msg}'}), 500
                
        except Exception as e:
            return jsonify({'error': f'Error de conexión con ImgBB: {str(e)}'}), 500


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
    pagos_multiples = datos.get('pagos_multiples', [])
    ruc_datos = datos.get('ruc', None)
    
    # Fallbacks por si viene el formato anterior
    metodo_pago_legacy = datos.get('metodo_pago', 'Efectivo')
    nombre_transferente_legacy = datos.get('nombre_transferente', None)

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
        incluye_ruc = 1 if ruc_datos else 0
        cursor.execute(
            "INSERT INTO Facturas (NumeroFactura, CodigoSeguimiento, UsuarioID, ClienteID, TurnoID, Subtotal, IVA, Total, EsEncargo, IncluyeRUC) "
            "OUTPUT INSERTED.ID "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            numero_factura, codigo_seguimiento, current_user.id, cliente_id, turno_id,
            subtotal, iva, total, 1 if es_encargo else 0, incluye_ruc
        )
        factura_id = cursor.fetchone()[0]

        # 4.1 Insertar datos de RUC si aplica
        if incluye_ruc and ruc_datos:
            cursor.execute(
                "INSERT INTO FacturasRUC (FacturaID, RazonSocial, NumeroRUC) VALUES (?, ?, ?)",
                factura_id, ruc_datos.get('razon_social', ''), ruc_datos.get('numero', '')
            )

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
                    nombre_extra = extra.get('nombre', '').strip()
                    precio_extra = float(extra.get('precio', 0))
                    
                    cursor.execute("SELECT ID FROM Ingredientes WHERE Nombre = ?", nombre_extra)
                    ing_row = cursor.fetchone()
                    
                    if ing_row:
                        ing_id = ing_row.ID
                    else:
                        cursor.execute(
                            "INSERT INTO Ingredientes (Nombre, PrecioAdicional, Activo) OUTPUT INSERTED.ID VALUES (?, ?, 1)",
                            nombre_extra, precio_extra
                        )
                        ing_id = cursor.fetchone()[0]
                    
                    cursor.execute(
                        "INSERT INTO DetalleIngredientes (DetalleFacturaID, IngredienteID, PrecioAplicado) "
                        "VALUES (?, ?, ?)",
                        detalle_id, ing_id, precio_extra
                    )

        # 5. Registrar el pago
        cambio_restante = float(datos.get('cambio', 0))
        
        if es_encargo and datos_encargo:
            adelanto = float(datos_encargo.get('adelanto', 0))
            metodo_adelanto = datos_encargo.get('metodo_adelanto', 'Efectivo')

            if adelanto > 0:
                cursor.execute(
                    "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente) VALUES (?, ?, ?, ?)",
                    factura_id, metodo_adelanto, adelanto,
                    nombre_transferente_legacy if metodo_adelanto == 'Transferencia' else None
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
            if pagos_multiples:
                for p in pagos_multiples:
                    monto = float(p.get('monto', 0))
                    metodo = p.get('metodo')
                    
                    # Deducir el cambio del efectivo recibido
                    if cambio_restante > 0 and metodo in ('Efectivo', 'Efectivo USD'):
                        if monto >= cambio_restante:
                            monto -= cambio_restante
                            cambio_restante = 0
                        else:
                            cambio_restante -= monto
                            monto = 0
                            
                    if monto > 0:
                        cursor.execute(
                            "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente) VALUES (?, ?, ?, ?)",
                            factura_id, metodo, monto,
                            p.get('referencia') if metodo == 'Transferencia' else None
                        )
            else:
                monto = float(total)
                cursor.execute(
                    "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente) VALUES (?, ?, ?, ?)",
                    factura_id, metodo_pago_legacy, monto,
                    nombre_transferente_legacy if metodo_pago_legacy == 'Transferencia' else None
                )

        # 5b. Fidelización: Sumar compra al cliente y subirlo de nivel si corresponde
        if cliente_id > 1:  # Ignoramos al Cliente General (ID 1)
            cursor.execute("UPDATE Clientes SET TotalCompras = ISNULL(TotalCompras, 0) + 1 WHERE ID = ?", cliente_id)
            cursor.execute("SELECT TotalCompras FROM Clientes WHERE ID = ?", cliente_id)
            compras_actuales = cursor.fetchone()[0]
            
            # 1: Nuevo, 2: Frecuente (>=3), 3: VIP (>=10)
            nuevo_nivel = 1
            if compras_actuales >= 10:
                nuevo_nivel = 3
            elif compras_actuales >= 3:
                nuevo_nivel = 2
                
            cursor.execute("UPDATE Clientes SET NivelConfianzaID = ? WHERE ID = ?", nuevo_nivel, cliente_id)

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
