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
        {'id': 1, 'nombre': 'Bolillo', 'precio': 5.00},
        {'id': 2, 'nombre': 'Pan Pizza', 'precio': 15.00},
        {'id': 3, 'nombre': 'Milanesa', 'precio': 25.00}
    ]
    return render_template('index.html', productos=productos)

@app.route('/api/venta', methods=['POST'])
def registrar_venta():
    datos = request.json
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad')
    
    if not producto_id or not cantidad:
        return jsonify({'error': 'Faltan datos'}), 400

    # Simular tiempo de procesamiento en servidor (1 segundo) para demostrar que no se bloquea la UI
    time.sleep(1)

    # TODO: Aquí irá la conexión a SQL Server
    # conn = pyodbc.connect(app.config['SQL_SERVER_CONNECTION_STRING'])
    # cursor = conn.cursor()
    # cursor.execute("INSERT INTO Ventas (ProductoID, Cantidad, Total) VALUES (?, ?, ?)", ...)
    # conn.commit()

    return jsonify({
        'status': 'success',
        'mensaje': 'Venta registrada con éxito de forma asíncrona',
        'producto_id': producto_id,
        'cantidad': cantidad
    }), 200

if __name__ == '__main__':
    app.run(debug=True)
