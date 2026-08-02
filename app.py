from flask import Flask, render_template, request, jsonify, url_for
from config import Config
import time
import uuid
import qrcode
import io
import base64
from datetime import datetime
# import pyodbc # Descomentar cuando se configure la conexión real

app = Flask(__name__)
app.config.from_object(Config)

# Contador global simulado (en producción vendrá de la BD)
factura_counter = 0
facturas_db = {}  # Almacén temporal en memoria para seguimiento

@app.route('/')
def index():
    # Simulamos los productos de la DB para el MVP
    productos = [
        {'id': 1, 'nombre': 'Bolillo', 'categoria': 'Mostrador', 'precio': 5.00},
        {'id': 2, 'nombre': 'Pan Pizza', 'categoria': 'Mostrador', 'precio': 15.00},
        {'id': 3, 'nombre': 'Milanesa', 'categoria': 'Mostrador', 'precio': 25.00},
        {'id': 4, 'nombre': 'Pastel 3 Leches', 'categoria': 'Encargo', 'precio': 350.00},
        {'id': 5, 'nombre': 'Pastel Chocolate', 'categoria': 'Encargo', 'precio': 400.00}
    ]
    ingredientes = [
        {'id': 1, 'nombre': 'Relleno de Fresa', 'precio': 50.00},
        {'id': 2, 'nombre': 'Relleno de Cajeta', 'precio': 40.00},
        {'id': 3, 'nombre': 'Cobertura de Chocolate', 'precio': 30.00},
        {'id': 4, 'nombre': 'Extra Nuez', 'precio': 60.00}
    ]
    return render_template('index.html', productos=productos, ingredientes=ingredientes)


def generar_qr_base64(data_url):
    """Genera un código QR y lo devuelve como imagen base64 para embeber en HTML."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"


@app.route('/api/factura', methods=['POST'])
def registrar_factura():
    global factura_counter
    datos = request.json
    carrito = datos.get('carrito', [])
    total = datos.get('total', 0)
    subtotal = datos.get('subtotal', 0)
    iva = datos.get('iva', 0)
    es_encargo = datos.get('es_encargo', False)
    datos_encargo = datos.get('encargo_detalles', None)

    if not carrito or total <= 0:
        return jsonify({'error': 'El carrito está vacío o el total es inválido'}), 400

    # Generar número de factura correlativo y código de seguimiento
    factura_counter += 1
    numero_factura = f"FAC-{factura_counter:04d}"
    codigo_seguimiento = uuid.uuid4().hex[:8].upper()

    # Simular tiempo de procesamiento en servidor
    time.sleep(0.5)

    # Generar URL de seguimiento y QR
    base_url = request.host_url.rstrip('/')
    url_seguimiento = f"{base_url}/seguimiento/{codigo_seguimiento}"
    qr_base64 = generar_qr_base64(url_seguimiento)

    # Construir datos de la factura para devolver al frontend
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

    # Guardar en memoria para seguimiento (en producción: SQL Server)
    facturas_db[codigo_seguimiento] = factura_data

    # TODO: Aquí irá la conexión a SQL Server
    # conn = pyodbc.connect(app.config['SQL_SERVER_CONNECTION_STRING'])
    # cursor = conn.cursor()
    #
    # cursor.execute(
    #     "INSERT INTO Facturas (NumeroFactura, CodigoSeguimiento, Subtotal, IVA, Total, TipoVenta) "
    #     "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, ?, ?)",
    #     numero_factura, codigo_seguimiento, subtotal, iva, total,
    #     'Encargo' if es_encargo else 'Contado'
    # )
    # factura_id = cursor.fetchone()[0]
    #
    # for item in carrito:
    #     cursor.execute(
    #         "INSERT INTO DetalleFacturas (FacturaID, ProductoID, NombreProducto, OpcionesExtra, Cantidad, PrecioUnitario, Subtotal) "
    #         "VALUES (?, ?, ?, ?, ?, ?, ?)",
    #         factura_id, item.get('id', 0), item['nombre'], item.get('opciones_extra', ''),
    #         item['cantidad'], item['precio'], item['subtotal']
    #     )
    #
    # if es_encargo and datos_encargo:
    #     cursor.execute(
    #         "INSERT INTO Encargos (FacturaID, NombreCliente, Telefono, FechaEntrega, Adelanto, SaldoPendiente) "
    #         "VALUES (?, ?, ?, ?, ?, ?)",
    #         factura_id, datos_encargo.get('nombre_cliente', ''),
    #         datos_encargo.get('telefono', ''), datos_encargo['fecha_entrega'],
    #         datos_encargo['adelanto'], datos_encargo['saldo']
    #     )
    #
    # conn.commit()

    return jsonify({
        'status': 'success',
        'mensaje': 'Factura registrada con éxito',
        'factura': factura_data
    }), 200


@app.route('/seguimiento/<codigo>')
def seguimiento(codigo):
    """Página pública para que el cliente vea el estado de su encargo."""
    factura = facturas_db.get(codigo)
    if not factura:
        return render_template('seguimiento.html', factura=None, codigo=codigo)
    return render_template('seguimiento.html', factura=factura, codigo=codigo)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
