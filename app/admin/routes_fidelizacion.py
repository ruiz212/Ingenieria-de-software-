# app/admin/routes_fidelizacion.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime
from app.services.validation import required_text

@admin_bp.route('/fidelizacion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def fidelizacion():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Métricas Globales
    cursor.execute("SELECT COUNT(ID) FROM Clientes WHERE ID > 1")
    total_clientes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(ID) FROM Clientes WHERE NivelConfianzaID = 3")
    total_vip = cursor.fetchone()[0]
    
    porcentaje_vip = int((total_vip / total_clientes * 100)) if total_clientes > 0 else 0

    # Promedio de ventas por nivel
    cursor.execute(
        "SELECT nc.Nombre, ISNULL(AVG(f.Total), 0) AS Promedio "
        "FROM Facturas f "
        "JOIN Clientes c ON f.ClienteID = c.ID "
        "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
        "WHERE f.EstadoFiscal='Emitida' GROUP BY nc.Nombre"
    )
    promedios_nivel = {r.Nombre: float(r.Promedio) for r in cursor.fetchall()}

    # Listado de clientes con gasto total
    cursor.execute(
        "SELECT c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre AS Nivel, "
        "ISNULL(SUM(f.Total), 0) AS TotalGastado, MAX(f.FechaHora) AS UltimaCompra "
        "FROM Clientes c "
        "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
        "LEFT JOIN Facturas f ON f.ClienteID = c.ID AND f.EstadoFiscal='Emitida' "
        "WHERE c.ID > 1 "
        "GROUP BY c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre "
        "ORDER BY c.TotalCompras DESC"
    )
    clientes = [{
        'id': r.ID,
        'nombre': r.Nombre,
        'telefono': r.Telefono or 'No registrado',
        'total_compras': r.TotalCompras,
        'nivel': r.Nivel,
        'total_gastado': float(r.TotalGastado),
        'ultima_compra': r.UltimaCompra.strftime('%d/%m/%Y') if r.UltimaCompra else 'N/A'
    } for r in cursor.fetchall()]

    conn.close()
    
    metricas = {
        'total_clientes': total_clientes,
        'porcentaje_vip': porcentaje_vip,
        'promedios_nivel': promedios_nivel
    }

    return render_template('admin/fidelizacion.html', user=current_user, clientes=clientes, metricas=metricas)


@admin_bp.route('/api/fidelizacion/clientes/<int:cliente_id>', methods=['GET'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def detalle_cliente(cliente_id):
    """Devuelve expediente e historial de compras de un cliente."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT ID, Nombre, Apellidos, Telefono, Genero, FechaNacimiento, "
            "RutaFotoPerfil, TotalCompras, NivelConfianzaID "
            "FROM Clientes WHERE ID = ? AND ID > 1",
            cliente_id
        )
        cliente = cursor.fetchone()
        if not cliente:
            return jsonify(error='Cliente no encontrado.'), 404

        cursor.execute(
            "SELECT ID, NumeroFactura, FechaHora, Subtotal, IVA, Total, EstadoFiscal "
            "FROM Facturas WHERE ClienteID = ? ORDER BY FechaHora DESC",
            cliente_id
        )
        historial = [
            {'id': row.ID, 'numero': row.NumeroFactura, 'fecha': row.FechaHora.isoformat(),
             'subtotal': float(row.Subtotal), 'iva': float(row.IVA), 'total': float(row.Total),
             'estado': row.EstadoFiscal}
            for row in cursor.fetchall()
        ]
        return jsonify(cliente={
            'id': cliente.ID, 'nombre': cliente.Nombre, 'apellidos': cliente.Apellidos,
            'telefono': cliente.Telefono, 'genero': cliente.Genero,
            'fecha_nacimiento': cliente.FechaNacimiento.isoformat() if cliente.FechaNacimiento else None,
            'foto': cliente.RutaFotoPerfil, 'total_compras': cliente.TotalCompras,
            'nivel_id': cliente.NivelConfianzaID, 'historial': historial
        })
    finally:
        conn.close()


@admin_bp.route('/api/fidelizacion/clientes/<int:cliente_id>', methods=['PUT'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def editar_cliente(cliente_id):
    """Actualiza datos de contacto y nivel de fidelidad del cliente."""
    data = request.get_json(silent=True) or {}
    nombre = required_text(data.get('nombre'), 'Nombre', 100)
    apellidos = (data.get('apellidos') or '').strip()[:100]
    telefono = required_text(data.get('telefono'), 'Teléfono', 30)
    nivel_id = data.get('nivel_id')
    if nivel_id is None:
        raise ValueError('Seleccione un nivel de fidelidad.')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT ID FROM Clientes WHERE Telefono = ? AND ID <> ?",
            telefono, cliente_id
        )
        if cursor.fetchone():
            return jsonify(error='El teléfono ya pertenece a otro cliente.'), 409
        cursor.execute("SELECT ID FROM NivelesConfianza WHERE ID = ?", int(nivel_id))
        if not cursor.fetchone():
            return jsonify(error='Nivel de fidelidad inexistente.'), 400
        cursor.execute(
            "UPDATE Clientes SET Nombre=?, Apellidos=?, Telefono=?, Genero=?, "
            "FechaNacimiento=?, NivelConfianzaID=? WHERE ID=? AND ID > 1",
            nombre, apellidos, telefono, data.get('genero'), data.get('fecha_nacimiento'),
            int(nivel_id), cliente_id
        )
        if cursor.rowcount != 1:
            return jsonify(error='Cliente no encontrado.'), 404
        conn.commit()
        return jsonify(status='success', mensaje='Cliente actualizado.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# MÓDULO DE ARQUEO DE CAJA v2 (Multi-Etapa)
# ============================================================


