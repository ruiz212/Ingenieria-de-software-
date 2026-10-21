# app/pos/routes.py
# Rutas del Punto de Venta y API de Facturas

import uuid
import os
import json
from datetime import datetime

from flask import render_template, request, jsonify, current_app, session
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user

from app.pos import pos_bp
from app.db import get_db_connection, execute_sp, is_sqlserver_cursor
from app.services.business_time import business_now
from app.services.reference_images import validate_reference_image
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
    execute_sp(
        cursor,
        'catalogo.sp_ObtenerCategoriasConProductosActivos',
        fallback_sql="""
        SELECT DISTINCT c.ID, c.Nombre 
        FROM Categorias c
        JOIN Productos p ON p.CategoriaID = c.ID
        WHERE p.Activo = 1
        ORDER BY c.Nombre
    """,
    )
    categorias = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    # Obtener productos activos con su categoría e imagen
    execute_sp(
        cursor,
        'catalogo.sp_ObtenerProductosPOS',
        fallback_sql=(
            "SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.PrecioBase, p.EsFicticio, p.PorcentajeDescuento, p.ImagenUrl, p.TasaIVA "
            "FROM Productos p "
            "JOIN Categorias c ON p.CategoriaID = c.ID "
            "WHERE p.Activo = 1 "
            "ORDER BY c.Nombre, p.Nombre"
        ),
    )
    productos = [
        {'id': row.ID, 'nombre': row.Nombre, 'categoria': row.Categoria,
         'precio': float(row.PrecioBase), 'es_ficticio': row.EsFicticio,
         'descuento': float(row.PorcentajeDescuento),
         'tasa_iva': float(row.TasaIVA) if row.TasaIVA is not None else None,
         'imagen_url': row.ImagenUrl or ''}
        for row in cursor.fetchall()
    ]

    # Obtener ingredientes extras activos
    execute_sp(
        cursor,
        'catalogo.sp_ObtenerIngredientesPOS',
        fallback_sql="SELECT ID, Nombre, PrecioAdicional FROM Ingredientes WHERE Activo = 1 ORDER BY Nombre",
    )
    ingredientes = [
        {'id': row.ID, 'nombre': row.Nombre, 'precio': float(row.PrecioAdicional)}
        for row in cursor.fetchall()
    ]

    # Obtener configuración del sistema (IVA, etc)
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerConfiguracionGlobal',
        fallback_sql="SELECT Clave, Valor FROM ConfiguracionSistema",
    )
    configuracion = {row.Clave: row.Valor for row in cursor.fetchall()}

    es_cliente = getattr(current_user, 'rol_nombre', '') in ['Cliente', 'Invitado']
    turno = None
    if not es_cliente:
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTurnoAbierto',
            (current_user.id,),
            fallback_sql="SELECT TOP 1 ID, FechaApertura FROM TurnosCaja WHERE UsuarioID = ? AND Cerrado = 0 ORDER BY ID DESC",
        )
        turno = cursor.fetchone()

    conn.close()

    template = 'tienda.html' if es_cliente else 'pos.html'

    return render_template(template,
                           productos=productos,
                           ingredientes=ingredientes,
                           categorias=categorias,
                           configuracion=configuracion,
                           user=current_user,
                           turno_activo=turno,
                           mes_actual=business_now().month)


@pos_bp.route('/api/turno/abrir', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def abrir_turno():
    """Abre explícitamente el turno del cajero antes de permitir ventas."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTurnoAbiertoBloqueo',
            (current_user.id,),
            fallback_sql=(
                "SELECT TOP 1 ID FROM TurnosCaja WITH (UPDLOCK, HOLDLOCK) "
                "WHERE UsuarioID = ? AND Cerrado = 0 ORDER BY ID DESC"
            ),
        )
        activo = cursor.fetchone()
        if activo:
            return jsonify(status='success', turno_id=activo.ID, existente=True)

        execute_sp(
            cursor,
            'ventas.sp_InsertarTurnoCaja',
            (current_user.id,),
            fallback_sql="INSERT INTO TurnosCaja (UsuarioID) OUTPUT INSERTED.ID VALUES (?)",
        )
        turno_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify(status='success', turno_id=turno_id, existente=False), 201
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error al abrir turno')
        return jsonify(error='No se pudo abrir el turno.'), 500
    finally:
        conn.close()

@pos_bp.route('/api/upload_referencia', methods=['POST'])
@login_required
def upload_referencia():
    if 'foto' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['foto']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if extension not in {'jpg', 'jpeg', 'png', 'webp'}:
        return jsonify({'error': 'Formato de imagen no permitido.'}), 400

    file.seek(0, os.SEEK_END)
    if file.tell() > 5 * 1024 * 1024:
        return jsonify({'error': 'La imagen no puede superar los 5 MB.'}), 400
    file.seek(0)
    
    if file:
        import requests
        import base64
        
        api_key = os.environ.get('IMGBB_API_KEY', '')
        
        if not api_key:
            upload_folder = os.path.join(current_app.static_folder, 'uploads', 'referencias')
            os.makedirs(upload_folder, exist_ok=True)
            filename = f"{uuid.uuid4().hex}.{extension}"
            file.save(os.path.join(upload_folder, filename))
            return jsonify({'ruta': f'uploads/referencias/{filename}'}), 200

        b64_image = base64.b64encode(file.read()).decode('utf-8')

        try:
            response = requests.post(
                'https://api.imgbb.com/1/upload',
                data={
                    'key': api_key,
                    'image': b64_image
                }, timeout=15
            )
            
            result = response.json()
            if result.get('success'):
                url_imagen = validate_reference_image(result['data']['url'])
                return jsonify({'ruta': url_imagen}), 200
            else:
                error_msg = result.get('error', {}).get('message', 'Error desconocido en ImgBB')
                return jsonify({'error': f'Error al subir a ImgBB: {error_msg}'}), 500
                
        except Exception as e:
            return jsonify({'error': f'Error de conexión con ImgBB: {str(e)}'}), 500


@pos_bp.route('/api/factura', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def registrar_factura():
    """Factura atómica: precio de catálogo, pagos conciliados y copia inmutable."""
    import hashlib
    from app.services.fiscal_service import configuration, calculate_sale, normalize_payments, next_invoice, audit
    from app.services.validation import amount, required_text
    from app.services.contabilidad_service import ContabilidadService, ContabilidadError
    datos = request.get_json()
    key = required_text(datos.get('clave_solicitud'), 'Identificador de operación', 64)
    fingerprint = hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Serializar reintentos antes de asignar número o registrar cobros.
        execute_sp(
            cursor,
            'ventas.sp_AdquirirLockFactura',
            ('factura:' + key,),
            fallback_sql="DECLARE @r INT; EXEC @r=sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @r",
        )
        if cursor.fetchone()[0] < 0:
            raise ValueError('La operación está en proceso. Reintente con el mismo carrito.')
        execute_sp(
            cursor,
            'ventas.sp_ObtenerFacturaPorClaveSolicitud',
            (key,),
            fallback_sql='SELECT UsuarioID,DocumentoJSON FROM Facturas WHERE ClaveSolicitud=?',
        )
        previous = cursor.fetchone()
        if previous:
            if previous[0] != current_user.id:
                return jsonify(error='Identificador de operación no disponible.'), 409
            saved = json.loads(previous[1])
            if saved.get('solicitud_hash') != fingerprint:
                return jsonify(error='La clave ya corresponde a otra venta. Recargue el carrito.'), 409
            return jsonify(status='success', factura=saved)
        config = configuration(cursor)
        carrito, subtotal, iva, total = calculate_sale(cursor, datos.get('carrito'), config)
        if total <= 0:
            raise ValueError('El total debe ser positivo.')
        es_encargo = datos.get('es_encargo') is True
        encargo = datos.get('encargo_detalles') if es_encargo else None
        if es_encargo and not isinstance(encargo, dict) and any(k in datos for k in ('adelanto', 'fecha_entrega', 'nombre_cliente', 'telefono')):
            encargo = {
                'adelanto': datos.get('adelanto', 0),
                'saldo': datos.get('saldo', 0),
                'metodo_adelanto': datos.get('metodo_adelanto', 'Efectivo'),
                'referencia': datos.get('referencia', ''),
                'fecha_entrega': datos.get('fecha_entrega', ''),
                'nombre_cliente': datos.get('nombre_cliente', ''),
                'telefono': datos.get('telefono', ''),
                'especificaciones': datos.get('especificaciones'),
                'ruta_imagen_referencia': datos.get('ruta_imagen_referencia'),
                'notas': datos.get('notas', ''),
                'monto_recibido': datos.get('monto_recibido'),
            }
        if es_encargo and not isinstance(encargo, dict):
            raise ValueError('Complete los datos del encargo.')
        delivery = None
        if es_encargo:
            encargo['ruta_imagen_referencia'] = validate_reference_image(encargo.get('ruta_imagen_referencia'))
            required_text(encargo.get('nombre_cliente'), 'Cliente', 100)
            required_text(encargo.get('telefono'), 'Teléfono', 20)
            delivery = datetime.fromisoformat(encargo.get('fecha_entrega', ''))
            if delivery.date() < business_now().date():
                raise ValueError('La entrega no puede ser anterior a hoy.')
            advance = amount(encargo.get('adelanto', 0))
            metodo_adelanto = encargo.get('metodo_adelanto', 'Efectivo')
            monto_pago = advance
            if metodo_adelanto == 'Efectivo' and encargo.get('monto_recibido') not in (None, ''):
                recibido = amount(encargo.get('monto_recibido'))
                if recibido >= advance:
                    monto_pago = recibido
            payments = [{'metodo': metodo_adelanto, 'monto': monto_pago,
                         'referencia': datos.get('nombre_transferente') or encargo.get('referencia', '')}]
            encargo = {**encargo, 'adelanto': float(advance), 'saldo': float(total - advance)}
        else:
            advance = None
            payments = datos.get('pagos_multiples') or [{'metodo': datos.get('metodo_pago', 'Efectivo'),
                          'monto': total, 'referencia': datos.get('nombre_transferente', '')}]
        if not isinstance(payments, list) or any(not isinstance(p, dict) for p in payments):
            raise ValueError('Pagos inválidos.')
        from decimal import Decimal
        exchange = Decimal(str(config.get('tipo_cambio_usd', '0')))
        if not exchange.is_finite() or exchange <= 0:
            raise ValueError('Configure un tipo de cambio positivo en ajustes.')
        if not es_encargo:
            payments = [{**p, 'monto': amount(p.get('monto'), 'Pago USD') * exchange} if p.get('metodo') == 'Efectivo USD' else p for p in payments]
        payments, change = normalize_payments(payments, total, advance)
        ruc = datos.get('ruc')
        if ruc:
            if not isinstance(ruc, dict):
                raise ValueError('Datos de RUC inválidos.')
            ruc = {'numero': required_text(ruc.get('numero'), 'RUC del cliente', 50),
                   'razon_social': required_text(ruc.get('razon_social'), 'Razón social del cliente', 255)}
        # Turno y venta comparten la misma transacción.
        execute_sp(
            cursor,
            'ventas.sp_ObtenerTurnoActivoParaVenta',
            (current_user.id,),
            fallback_sql='SELECT ID FROM TurnosCaja WITH (UPDLOCK,HOLDLOCK) WHERE UsuarioID=? AND Cerrado=0',
        )
        shift = cursor.fetchone()
        if shift:
            turno_id = shift[0]
            execute_sp(
                cursor,
                'ventas.sp_VerificarArqueoPendienteTurno',
                (turno_id,),
                fallback_sql="SELECT ID FROM ArqueoCaja WHERE TurnoID=? AND EstadoArqueo IN ('Pendiente','Verificado')",
            )
            if cursor.fetchone():
                raise ValueError('La caja tiene un arqueo pendiente. Finalice la verificación antes de vender.')
        else:
            raise ValueError('Debe abrir un turno antes de registrar ventas.')
        cliente_id = 1
        if es_encargo:
            execute_sp(
                cursor,
                'crm.sp_ObtenerClientePorTelefono',
                (encargo['telefono'],),
                fallback_sql='SELECT ID FROM Clientes WHERE Telefono=?',
            )
            client = cursor.fetchone()
            if client:
                cliente_id = client[0]
            else:
                execute_sp(
                    cursor,
                    'crm.sp_InsertarClienteRapido',
                    (encargo['nombre_cliente'], encargo['telefono']),
                    fallback_sql='INSERT INTO Clientes(Nombre,Telefono,NivelConfianzaID) OUTPUT INSERTED.ID VALUES(?,?,1)',
                )
                cliente_id = cursor.fetchone()[0]
        number = next_invoice(cursor, config.get('fiscal_serie', 'FAC'))
        code = uuid.uuid4().hex[:10].upper()
        issued_at = business_now()

        if is_sqlserver_cursor(cursor):
            pagos_payload = [
                {
                    'metodo': p['metodo'],
                    'monto': float(p['monto']),
                    'referencia': p['referencia'] or None,
                    'tipo_cambio': float(exchange) if p['metodo'] == 'Efectivo USD' else None,
                }
                for p in payments
            ]
            execute_sp(
                cursor,
                'ventas.sp_RegistrarFacturaCompleta',
                (
                    number,
                    code,
                    current_user.id,
                    cliente_id,
                    turno_id,
                    subtotal,
                    iva,
                    total,
                    1 if es_encargo else 0,
                    1 if ruc else 0,
                    key,
                    issued_at,
                    ruc['razon_social'] if ruc else None,
                    ruc['numero'] if ruc else None,
                    json.dumps(carrito, ensure_ascii=False),
                    json.dumps(pagos_payload, ensure_ascii=False),
                    delivery if es_encargo else None,
                    encargo.get('notas', '') if es_encargo else None,
                    encargo.get('especificaciones') if es_encargo else None,
                    encargo.get('ruta_imagen_referencia') if es_encargo else None,
                    encargo['telefono'] if es_encargo else None,
                ),
            )
            factura_id = cursor.fetchone()[0]
        else:
            execute_sp(
                cursor,
                'ventas.sp_InsertarFacturaCabecera',
                (number, code, current_user.id, cliente_id, turno_id, subtotal, iva, total, es_encargo, bool(ruc), key, issued_at),
                fallback_sql="INSERT INTO Facturas(NumeroFactura,CodigoSeguimiento,UsuarioID,ClienteID,TurnoID,Subtotal,IVA,Total,EsEncargo,IncluyeRUC,ClaveSolicitud,FechaHora) OUTPUT INSERTED.ID VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            )
            factura_id = cursor.fetchone()[0]
            if ruc:
                execute_sp(
                    cursor,
                    'ventas.sp_InsertarFacturaRUC',
                    (factura_id, ruc['razon_social'], ruc['numero']),
                    fallback_sql='INSERT INTO FacturasRUC(FacturaID,RazonSocial,NumeroRUC) VALUES(?,?,?)',
                )
            for item in carrito:
                execute_sp(
                    cursor,
                    'ventas.sp_InsertarDetalleFactura',
                    (factura_id, item['id'], item['cantidad'], amount(item['precio']), amount(item['subtotal'])),
                    fallback_sql='INSERT INTO DetalleFacturas(FacturaID,ProductoID,Cantidad,PrecioUnitario,Subtotal) OUTPUT INSERTED.ID VALUES(?,?,?,?,?)',
                )
                detail_id = cursor.fetchone()[0]
                for extra in item['detalle_ingredientes']['ingredientes']:
                    execute_sp(
                        cursor,
                        'ventas.sp_InsertarDetalleIngrediente',
                        (detail_id, extra['id'], amount(extra['precio'])),
                        fallback_sql='INSERT INTO DetalleIngredientes(DetalleFacturaID,IngredienteID,PrecioAplicado) VALUES(?,?,?)',
                    )
                if item.get('cotizacion_id'):
                    execute_sp(
                        cursor,
                        'crm.sp_MarcarCotizacionAceptadaEnVenta',
                        (item['cotizacion_id'],),
                        fallback_sql="UPDATE Cotizaciones SET Estado='Aceptada' WHERE ID=? AND Estado IN ('Cotizada','Aceptada')",
                    )
            for payment in payments:
                execute_sp(
                    cursor,
                    'ventas.sp_InsertarPagoFactura',
                    (factura_id, payment['metodo'], payment['monto'], payment['referencia'] or None, exchange if payment['metodo'] == 'Efectivo USD' else None),
                    fallback_sql="INSERT INTO Pagos(FacturaID,MetodoPago,Monto,NombreTransferente,MonedaRegistro,TipoCambioAplicado) VALUES(?,?,?,?,'NIO',?)",
                )
            if es_encargo:
                execute_sp(
                    cursor,
                    'produccion.sp_InsertarEncargo',
                    (factura_id, delivery, encargo.get('notas', ''), encargo.get('especificaciones'), encargo.get('ruta_imagen_referencia'), encargo['telefono']),
                    fallback_sql="INSERT INTO Encargos(FacturaID,FechaEntrega,Estado,NotasCliente,Especificaciones,RutaImagenReferencia,TelefonoContacto) VALUES(?,?,'Pendiente',?,?,?,?)",
                )
            if cliente_id > 1:
                execute_sp(
                    cursor,
                    'crm.sp_IncrementarComprasCliente',
                    (cliente_id,),
                    fallback_sql='UPDATE Clientes SET TotalCompras=ISNULL(TotalCompras,0)+1 WHERE ID=?',
                )
                execute_sp(
                    cursor,
                    'crm.sp_ActualizarNivelConfianzaCliente',
                    (cliente_id,),
                    fallback_sql='UPDATE Clientes SET NivelConfianzaID=CASE WHEN TotalCompras>=10 THEN 3 WHEN TotalCompras>=3 THEN 2 ELSE 1 END WHERE ID=?',
                )
        entry = ContabilidadService.contabilizar_venta(cursor, current_user.id, number, subtotal, iva, total, payments, es_encargo, advance or 0, request.remote_addr, fecha=issued_at)
        now = issued_at
        link = request.host_url.rstrip('/') + '/seguimiento/' + code
        document = {'id': factura_id, 'numero_factura': number, 'codigo_seguimiento': code, 'solicitud_hash': fingerprint,
            'fecha': now.strftime('%d/%m/%Y'), 'hora': now.strftime('%H:%M:%S'), 'zona_horaria': 'America/Managua',
            'productos': carrito, 'subtotal': float(subtotal), 'iva': float(iva), 'total': float(total),
            'cambio': float(change), 'es_encargo': es_encargo, 'encargo_detalles': encargo,
            'tipo_cambio': str(exchange), 'pagos': [dict(p, monto=float(p['monto'])) for p in payments],
            'qr_image': generar_qr_base64(link), 'url_seguimiento': link, 'asiento_id': entry['asiento_id'],
            'emisor': {k: v for k, v in config.items() if k.startswith('fiscal_')}, 'ruc': ruc,
            'condicion': 'Crédito' if es_encargo and advance < total else 'Contado',
            'aviso': 'COMPROBANTE DE PRUEBA SIN VALIDEZ FISCAL' if config.get('fiscal_regimen', 'Pendiente') == 'Pendiente' else '',
            'url_impresion': f'/admin/fiscal/facturas/{factura_id}/imprimir'}
        execute_sp(
            cursor,
            'ventas.sp_ActualizarDocumentoJSONFactura',
            (json.dumps(document, ensure_ascii=False), factura_id),
            fallback_sql='UPDATE Facturas SET DocumentoJSON=? WHERE ID=?',
        )
        audit(cursor, current_user.id, 'EMISION', 'Factura', factura_id, {'numero': number, 'total': total}, request.remote_addr)
        conn.commit()
        return jsonify(status='success', mensaje='Factura registrada', factura=document)
    except (ValueError, ContabilidadError) as error:
        conn.rollback()
        return jsonify(error=str(error)), 400
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error registrando factura')
        return jsonify(error='No se registró la venta. Intente de nuevo con el mismo carrito.'), 500
    finally:
        conn.close()

# ============================================================
# API DE COTIZACIONES DE PASTELES PERSONALIZADOS
# ============================================================


def _puede_gestionar_cotizacion(row):
    """Propiedad por identidad o token privado; un teléfono no autoriza."""
    if getattr(current_user, 'rol_nombre', '') in ('Estandar', 'Admin', 'SuperAdmin'):
        return True
    registered = getattr(current_user, 'rol_nombre', '') == 'Cliente' and not getattr(current_user, 'es_invitado', False)
    if row.ClienteID is not None:
        return registered and row.ClienteID == current_user.id
    token = session.get('cotizacion_session_id')
    return bool(token and row.SessionID and token == row.SessionID)

@pos_bp.route('/api/cotizaciones', methods=['POST'])
@login_required
def crear_cotizacion():
    datos = request.json or {}
    especificaciones = datos.get('especificaciones')
    fecha_entrega = datos.get('fecha_entrega')
    ruta_imagen = validate_reference_image(datos.get('ruta_imagen_referencia'))
    telefono = datos.get('telefono')
    nombre_contacto = datos.get('nombre')  # Para invitados

    if not especificaciones or not fecha_entrega:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    es_cliente_registrado = getattr(current_user, 'rol_nombre', '') == 'Cliente' and not getattr(current_user, 'es_invitado', False)
    cliente_id = current_user.id if es_cliente_registrado else None
    
    telefono = telefono or getattr(current_user, 'telefono', None)
    nombre_contacto = nombre_contacto or getattr(current_user, 'nombre', None)
    
    # Para invitados, usamos un Session ID
    session_id = None
    if not cliente_id:
        if 'cotizacion_session_id' not in session:
            session['cotizacion_session_id'] = str(uuid.uuid4())
        session_id = session['cotizacion_session_id']
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'crm.sp_CrearCotizacion',
            (cliente_id, session_id, especificaciones, fecha_entrega, ruta_imagen, telefono, nombre_contacto),
            fallback_sql=(
                "SET NOCOUNT ON; INSERT INTO Cotizaciones (ClienteID, SessionID, Especificaciones, FechaEntrega, RutaImagenReferencia, TelefonoContacto, Estado, NombreContacto) "
                "OUTPUT INSERTED.ID "
                "VALUES (?, ?, ?, ?, ?, ?, 'Pendiente', ?)"
            ),
        )
        cotizacion_id = cursor.fetchone()[0]
        numero_cotizacion = f"COT-{cotizacion_id:04d}"
        
        conn.commit()
        return jsonify({
            'mensaje': 'Cotización solicitada correctamente',
            'numero_cotizacion': numero_cotizacion
        }), 200
    except Exception as e:
        conn.rollback()
        current_app.logger.exception("Error al crear cotización")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@pos_bp.route('/api/cotizaciones/cliente', methods=['GET'])
@login_required
def obtener_cotizaciones_cliente():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        es_cliente_registrado = getattr(current_user, 'rol_nombre', '') == 'Cliente' and not getattr(current_user, 'es_invitado', False)
        cliente_id = current_user.id if es_cliente_registrado else None
        session_id = session.get('cotizacion_session_id')
        
        # Sólo un token privado de este navegador puede vincular solicitudes previas.
        if cliente_id:
            if session_id:
                execute_sp(
                    cursor,
                    'crm.sp_VincularCotizacionesSesionCliente',
                    (cliente_id, session_id),
                    fallback_sql="UPDATE Cotizaciones SET ClienteID = ? WHERE ClienteID IS NULL AND SessionID = ?",
                )
            conn.commit()
            
            execute_sp(
                cursor,
                'crm.sp_ObtenerCotizacionesPorClienteID',
                (cliente_id,),
                fallback_sql=(
                    "SELECT ID, Especificaciones, FechaEntrega, RutaImagenReferencia, Estado, PrecioCotizado, TelefonoContacto "
                    "FROM Cotizaciones "
                    "WHERE ClienteID = ? "
                    "ORDER BY FechaSolicitud DESC"
                ),
            )
        elif session_id:
            execute_sp(
                cursor,
                'crm.sp_ObtenerCotizacionesPorSessionID',
                (session_id,),
                fallback_sql=(
                    "SELECT ID, Especificaciones, FechaEntrega, RutaImagenReferencia, Estado, PrecioCotizado, TelefonoContacto "
                    "FROM Cotizaciones "
                    "WHERE ClienteID IS NULL AND SessionID = ? "
                    "ORDER BY FechaSolicitud DESC"
                ),
            )
        else:
            return jsonify([])
            
        cotizaciones = []
        for row in cursor.fetchall():
            cotizaciones.append({
                'id': row.ID,
                'especificaciones': row.Especificaciones or '',
                'fecha_entrega': row.FechaEntrega.strftime('%Y-%m-%d') if row.FechaEntrega else '',
                'ruta_imagen': row.RutaImagenReferencia or '',
                'estado': row.Estado,
                'precio_cotizado': float(row.PrecioCotizado) if row.PrecioCotizado is not None else None,
                'telefono': row.TelefonoContacto or ''
            })
        
        return jsonify(cotizaciones)
    except Exception as e:
        current_app.logger.exception("Error al obtener cotizaciones del cliente")
        return jsonify({'error': 'Error al obtener cotizaciones: ' + str(e)}), 500
    finally:
        conn.close()

@pos_bp.route('/api/cotizaciones/pendientes', methods=['GET'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def obtener_cotizaciones_pendientes():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    execute_sp(
        cursor,
        'crm.sp_ObtenerCotizacionesPendientesAdmin',
        fallback_sql="""
        SELECT c.*, cl.Nombre AS ClienteNombre 
        FROM Cotizaciones c
        LEFT JOIN Clientes cl ON c.ClienteID = cl.ID
        WHERE c.Estado IN ('Pendiente', 'Cotizada', 'Aceptada')
        ORDER BY CASE WHEN c.Estado = 'Pendiente' THEN 0 ELSE 1 END, c.FechaSolicitud ASC
    """,
    )
    
    cotizaciones = []
    for row in cursor.fetchall():
        cotizaciones.append({
            'id': row.ID,
            'cliente': row.ClienteNombre or getattr(row, 'NombreContacto', None) or 'Invitado',
            'telefono': row.TelefonoContacto,
            'especificaciones': row.Especificaciones,
            'fecha_entrega': row.FechaEntrega.strftime('%Y-%m-%d') if row.FechaEntrega else '',
            'ruta_imagen': row.RutaImagenReferencia,
            'estado': row.Estado,
            'precio_cotizado': float(row.PrecioCotizado) if getattr(row, 'PrecioCotizado', None) is not None else None,
            'fecha_solicitud': row.FechaSolicitud.strftime('%Y-%m-%d %H:%M')
        })
        
    conn.close()
    return jsonify(cotizaciones)

@pos_bp.route('/api/cotizaciones/<int:id>/cotizar', methods=['POST'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
def cotizar_pedido(id):
    datos = request.json
    from app.services.validation import amount
    precio = amount(datos.get('precio'), 'Precio cotizado', minimum=0.01)
    
    if not precio:
        return jsonify({'error': 'Precio es requerido'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        execute_sp(
            cursor,
            'crm.sp_CotizarPedidoAdmin',
            (precio, id),
            fallback_sql="UPDATE Cotizaciones SET PrecioCotizado = ?, Estado = 'Cotizada' WHERE ID = ? AND Estado IN ('Pendiente','Cotizada')",
        )
        if cursor.rowcount != 1:
            return jsonify(error='Cotización inexistente o ya procesada.'), 409
        conn.commit()
        return jsonify({'mensaje': 'Cotización enviada'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@pos_bp.route('/api/cotizaciones/<int:id>/rechazar', methods=['POST'])
@login_required
def rechazar_cotizacion(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        execute_sp(
            cursor,
            'crm.sp_ObtenerCotizacionPorIDBloqueo',
            (id,),
            fallback_sql='SELECT ClienteID, SessionID, Estado, TelefonoContacto FROM Cotizaciones WITH(UPDLOCK,HOLDLOCK) WHERE ID=?',
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(error='Cotización no encontrada.'), 404

        if not _puede_gestionar_cotizacion(row):
            return jsonify(error='Cotización no disponible para este usuario.'), 403

        if row.Estado not in ('Pendiente', 'Cotizada'):
            return jsonify(error='La cotización ya no se puede rechazar.'), 409

        execute_sp(
            cursor,
            'crm.sp_CancelarCotizacionCliente',
            (id,),
            fallback_sql="UPDATE Cotizaciones SET Estado='Rechazada' WHERE ID=?",
        )
        conn.commit()
        return jsonify({'mensaje': 'Cotización rechazada'}), 200
    except Exception as e:
        conn.rollback()
        current_app.logger.exception("Error al rechazar cotización")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@pos_bp.route('/api/cotizaciones/<int:id>/aceptar', methods=['POST'])
@login_required
def aceptar_cotizacion(id):
    """Permite al cliente aceptar una cotización propia ya valorada."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'crm.sp_ObtenerCotizacionParaAceptarBloqueo',
            (id,),
            fallback_sql='SELECT ClienteID, SessionID, Estado, PrecioCotizado, TelefonoContacto FROM Cotizaciones WITH(UPDLOCK,HOLDLOCK) WHERE ID=?',
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(error='Cotización no encontrada.'), 404

        es_cliente_registrado = getattr(current_user, 'rol_nombre', '') == 'Cliente' and not getattr(current_user, 'es_invitado', False)
        cliente_id = current_user.id if es_cliente_registrado else None
        if not _puede_gestionar_cotizacion(row):
            return jsonify(error='Cotización no disponible para este usuario.'), 403

        if row.Estado != 'Cotizada' or row.PrecioCotizado is None:
            if row.Estado == 'Aceptada':
                return jsonify(mensaje='Cotización ya aceptada', id=id, precio_cotizado=float(row.PrecioCotizado or 0)), 200
            return jsonify(error='La cotización todavía no está lista para aceptar.'), 409

        # Vincular ClienteID si faltaba
        if row.ClienteID is None and cliente_id:
            execute_sp(
                cursor,
                'crm.sp_VincularCotizacionPorID',
                (cliente_id, id),
                fallback_sql="UPDATE Cotizaciones SET ClienteID = ? WHERE ID = ?",
            )

        execute_sp(
            cursor,
            'crm.sp_AceptarCotizacionCliente',
            (id,),
            fallback_sql="UPDATE Cotizaciones SET Estado='Aceptada' WHERE ID=? AND Estado='Cotizada'",
        )
        if cursor.rowcount != 1:
            return jsonify(error='La cotización cambió. Actualice la pantalla.'), 409

        conn.commit()
        return jsonify(mensaje='Cotización aceptada', id=id, precio_cotizado=float(row.PrecioCotizado)), 200
    except Exception as error:
        conn.rollback()
        current_app.logger.exception("Error al aceptar cotización")
        return jsonify(error=str(error)), 500
    finally:
        conn.close()
