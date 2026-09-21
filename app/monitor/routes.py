# app/monitor/routes.py
# Rutas del Monitor de Producción y Seguimiento Público de Encargos

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.monitor import monitor_bp
from app.db import get_db_connection
from app.extensions import csrf
from app.auth.decorators import roles_required


# ============================================================
# SEGUIMIENTO PÚBLICO DE ENCARGOS (sin login)
# ============================================================

@monitor_bp.route('/seguimiento/<codigo>')
def seguimiento(codigo):
    """Página pública para que el cliente vea el estado de su encargo."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT f.NumeroFactura, f.FechaHora, f.Total, f.Subtotal, f.IVA, "
        "       e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones, e.RutaImagenReferencia, "
        "       c.Nombre AS NombreCliente "
        "FROM Facturas f "
        "JOIN Encargos e ON e.FacturaID = f.ID "
        "LEFT JOIN Clientes c ON f.ClienteID = c.ID "
        "WHERE f.CodigoSeguimiento = ?", codigo
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return render_template('seguimiento.html', factura=None, codigo=codigo)

    # Obtener el adelanto (suma de pagos realizados hasta el momento)
    cursor.execute(
        "SELECT ISNULL(SUM(Monto), 0) FROM Pagos "
        "WHERE FacturaID = (SELECT ID FROM Facturas WHERE CodigoSeguimiento = ?)", codigo
    )
    adelanto = float(cursor.fetchone()[0])
    saldo = float(row.Total) - adelanto

    # Obtener productos del encargo
    cursor.execute(
        "SELECT p.Nombre, df.Cantidad, df.PrecioUnitario, df.Subtotal "
        "FROM DetalleFacturas df "
        "JOIN Productos p ON df.ProductoID = p.ID "
        "JOIN Facturas f ON df.FacturaID = f.ID "
        "WHERE f.CodigoSeguimiento = ?", codigo
    )
    productos = [
        {'nombre': r.Nombre, 'cantidad': r.Cantidad,
         'precio': float(r.PrecioUnitario), 'subtotal': float(r.Subtotal)}
        for r in cursor.fetchall()
    ]
    conn.close()

    factura = {
        'numero_factura': row.NumeroFactura,
        'fecha': row.FechaHora.strftime('%d/%m/%Y'),
        'hora': row.FechaHora.strftime('%H:%M:%S'),
        'total': float(row.Total),
        'subtotal': float(row.Subtotal),
        'iva': float(row.IVA),
        'productos': productos,
        'es_encargo': True,
        'encargo_detalles': {
            'estado': row.Estado,
            'fecha_entrega': row.FechaEntrega.strftime('%d/%m/%Y') if row.FechaEntrega else '',
            'notas': row.NotasCliente or '',
            'especificaciones': row.Especificaciones or '',
            'ruta_imagen_referencia': row.RutaImagenReferencia or '',
            'nombre_cliente': row.NombreCliente or 'N/A',
            'adelanto': adelanto,
            'saldo': saldo
        }
    }
    return render_template('seguimiento.html', factura=factura, codigo=codigo)


# ============================================================
# MONITOR INTERNO DE PRODUCCIÓN (requiere login)
# ============================================================

@monitor_bp.route('/monitor')
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Invitado', 'Operativo')
def monitor_pedidos():
    """Panel interno para que la panadería vea y actualice los pedidos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT f.ID, f.NumeroFactura, f.CodigoSeguimiento, f.FechaHora, f.Total, "
        "       e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones, e.RutaImagenReferencia, e.TelefonoContacto, "
        "       c.Nombre AS ClienteNombre, c.Telefono AS ClienteTelefono "
        "FROM Facturas f "
        "JOIN Encargos e ON e.FacturaID = f.ID "
        "LEFT JOIN Clientes c ON f.ClienteID = c.ID "
        "WHERE e.Estado != 'Entregado' "
        "ORDER BY e.FechaEntrega ASC"
    )
    encargos = []
    for row in cursor.fetchall():
        encargos.append({
            'numero_factura': row.NumeroFactura,
            'codigo_seguimiento': row.CodigoSeguimiento,
            'fecha': row.FechaHora.strftime('%d/%m/%Y %H:%M'),
            'total': float(row.Total),
            'es_encargo': True,
            'encargo_detalles': {
                'estado': row.Estado,
                'fecha_entrega': row.FechaEntrega.strftime('%d/%m/%Y') if row.FechaEntrega else '',
                'notas': row.NotasCliente or '',
                'especificaciones': row.Especificaciones or '',
                'ruta_imagen_referencia': row.RutaImagenReferencia or '',
                'nombre_cliente': row.ClienteNombre or 'Cliente General',
                'telefono': row.TelefonoContacto or row.ClienteTelefono or ''
            }
        })
    conn.close()
    return render_template('monitor.html', encargos=encargos, user=current_user)


# ============================================================
# API: ACTUALIZAR ESTADO DE ENCARGO
# ============================================================

@monitor_bp.route('/api/seguimiento/<codigo>/estado', methods=['PUT'])
@csrf.exempt
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Operativo')
def actualizar_estado(codigo):
    """Actualiza el estado de un encargo en la BD."""
    data = request.get_json()
    nuevo_estado = data.get('estado')

    estados_validos = ['Pendiente', 'En Proceso', 'Listo', 'Entregado']
    if nuevo_estado not in estados_validos:
        return jsonify({'error': 'Estado inválido'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Encargos SET Estado = ? "
            "FROM Encargos e JOIN Facturas f ON e.FacturaID = f.ID "
            "WHERE f.CodigoSeguimiento = ?",
            nuevo_estado, codigo
        )
        if cursor.rowcount == 0:
            return jsonify({'error': 'Encargo no encontrado'}), 404

        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Estado actualizado',
            'nuevo_estado': nuevo_estado
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
