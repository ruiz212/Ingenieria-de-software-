from flask import Flask, render_template, request, jsonify
from config import Config
import time
# import pyodbc # Descomentar cuando se configure la conexión real

app = Flask(__name__)
app.config.from_object(Config)

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

@app.route('/api/factura', methods=['POST'])
def registrar_factura():
    datos = request.json
    carrito = datos.get('carrito', [])
    total = datos.get('total', 0)
    es_encargo = datos.get('es_encargo', False)
    datos_encargo = datos.get('encargo_detalles', None)
    
    if not carrito or total <= 0:
        return jsonify({'error': 'El carrito está vacío o el total es inválido'}), 400

    # Simular tiempo de procesamiento en servidor para demostrar asincronismo sin bloqueo UI
    time.sleep(1)

    # TODO: Aquí irá la conexión a SQL Server
    # conn = pyodbc.connect(app.config['SQL_SERVER_CONNECTION_STRING'])
    # cursor = conn.cursor()
    # 
    # 1. Insertar en Facturas -> obtener FacturaID
    # tipo_venta = 'Encargo' if es_encargo else 'Contado'
    # cursor.execute("INSERT INTO Facturas (Total, TipoVenta) OUTPUT INSERTED.ID VALUES (?, ?)", total, tipo_venta)
    # factura_id = cursor.fetchone()[0]
    #
    # 2. Iterar carrito e insertar en DetalleFacturas
    # for item in carrito:
    #     cursor.execute("INSERT INTO DetalleFacturas (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal) VALUES (?, ?, ?, ?, ?)", factura_id, item['id'], item['cantidad'], item['precio'], item['subtotal'])
    #
    # 3. Si es encargo, insertar en tabla Encargos
    # if es_encargo and datos_encargo:
    #     cursor.execute("INSERT INTO Encargos (FacturaID, FechaEntrega, Adelanto, SaldoPendiente) VALUES (?, ?, ?, ?)", factura_id, datos_encargo['fecha_entrega'], datos_encargo['adelanto'], datos_encargo['saldo'])
    #
    # conn.commit()

    return jsonify({
        'status': 'success',
        'mensaje': 'Factura registrada con éxito',
        'factura_simulada_id': 1001,
        'encargo': es_encargo
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
