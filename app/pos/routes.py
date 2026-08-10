# app/pos/routes.py
# Rutas del Punto de Venta y API de Facturas

import uuid
from datetime import datetime

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.pos import pos_bp
from app.db import get_db_connection, obtener_o_crear_turno
from app.extensions import csrf
from app.utils.qr import generar_qr_base64
from app.auth.decorators import roles_required


@pos_bp.route('/pos')
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin')
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
                           user=current_user)


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
        # 1. Obtener o crear turno activo
        turno_id = obtener_o_crear_turno(current_user.id)

        # 2. Generar número de factura correlativo desde la BD
        cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 FROM Facturas")
        siguiente_num = cursor.fetchone()[0]
        numero_factura = f"FAC-{siguiente_num:04d}"
        codigo_seguimiento = uuid.uuid4().hex[:8].upper()

        # 3. Determinar ClienteID y guardar datos del cliente si es encargo
        cliente_id = 1 # Cliente General por defecto
        
        if es_encargo and datos_encargo:
            nombre_cli = datos_encargo.get('nombre_cliente', '').strip()
            telefono_cli = datos_encargo.get('telefono', '').strip()
            
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
            cursor.execute(
                "INSERT INTO Encargos (FacturaID, FechaEntrega, Estado, NotasCliente) VALUES (?, ?, 'Pendiente', ?)",
                factura_id, fecha_entrega, datos_encargo.get('notas', '')
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
