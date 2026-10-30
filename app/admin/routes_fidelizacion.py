# app/admin/routes_fidelizacion.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import re
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime
from app.services.validation import required_text, validate_telefono_nicaragua
from app.services.auth_challenges import normalize_phone


DUPLICATE_PHONE_MSG = 'El teléfono ya pertenece a otro cliente.'


def normalize_customer_phone(raw_phone: str | None) -> str:
    """Normaliza y valida teléfonos de clientes (con o sin +505, guiones, espacios o paréntesis) a 8 dígitos canónicos."""
    return validate_telefono_nicaragua(raw_phone, 'Teléfono', optional=False, as_digits=True)


def _is_duplicate_phone_error(exc: Exception) -> bool:
    msg = str(exc or '').lower()
    return (
        '52020' in msg
        or 'pertenece a otro cliente' in msg
        or 'ux_clientes_telefono' in msg
        or '2601' in msg
        or '2627' in msg
    )


@admin_bp.route('/fidelizacion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def fidelizacion():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Métricas Globales
    execute_sp(
        cursor,
        'crm.sp_ContarClientesReales',
        fallback_sql="SELECT COUNT(ID) FROM Clientes WHERE ID > 1",
    )
    total_clientes = cursor.fetchone()[0]

    execute_sp(
        cursor,
        'crm.sp_ContarClientesVIP',
        fallback_sql="SELECT COUNT(ID) FROM Clientes WHERE NivelConfianzaID = 3",
    )
    total_vip = cursor.fetchone()[0]

    porcentaje_vip = int((total_vip / total_clientes * 100)) if total_clientes > 0 else 0

    # Promedio de ventas por nivel
    execute_sp(
        cursor,
        'crm.sp_ObtenerPromedioVentasPorNivel',
        fallback_sql=(
            "SELECT nc.Nombre, ISNULL(AVG(f.Total), 0) AS Promedio "
            "FROM Facturas f "
            "JOIN Clientes c ON f.ClienteID = c.ID "
            "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
            "WHERE f.EstadoFiscal='Emitida' GROUP BY nc.Nombre"
        ),
    )
    promedios_nivel = {r.Nombre: float(r.Promedio) for r in cursor.fetchall()}

    # Listado de clientes con gasto total vía SP
    execute_sp(
        cursor,
        'crm.sp_ListarClientesFidelizacion',
        fallback_sql=(
            "SELECT c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre AS Nivel, "
            "ISNULL(SUM(f.Total), 0) AS TotalGastado, MAX(f.FechaHora) AS UltimaCompra "
            "FROM Clientes c "
            "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
            "LEFT JOIN Facturas f ON f.ClienteID = c.ID AND f.EstadoFiscal='Emitida' "
            "WHERE c.ID > 1 "
            "GROUP BY c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre "
            "ORDER BY c.TotalCompras DESC"
        ),
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
    """Devuelve expediente e historial de compras de un cliente vía SP."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'crm.sp_ObtenerExpedienteCliente',
            (cliente_id,),
            fallback_sql=(
                "SELECT ID, Nombre, Apellidos, Telefono, Genero, FechaNacimiento, "
                "RutaFotoPerfil, TotalCompras, NivelConfianzaID "
                "FROM Clientes WHERE ID = ? AND ID > 1"
            ),
        )
        cliente = cursor.fetchone()
        if not cliente:
            return jsonify(error='Cliente no encontrado.'), 404

        execute_sp(
            cursor,
            'ventas.sp_ObtenerHistorialFacturasCliente',
            (cliente_id,),
            fallback_sql=(
                "SELECT ID, NumeroFactura, FechaHora, Subtotal, IVA, Total, EstadoFiscal "
                "FROM Facturas WHERE ClienteID = ? ORDER BY FechaHora DESC"
            ),
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


@admin_bp.route('/api/fidelizacion/clientes', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_cliente():
    """Registra un nuevo cliente normalizando su teléfono y validando unicidad bajo bloqueo."""
    data = request.get_json(silent=True) or {}
    try:
        nombre = required_text(data.get('nombre'), 'Nombre', 100)
        apellidos = (data.get('apellidos') or '').strip()[:100]
        telefono = normalize_customer_phone(data.get('telefono'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'crm.sp_VerificarTelefonoClienteDuplicado',
            (telefono, 0),
            fallback_sql=(
                "SELECT ID FROM Clientes WITH (UPDLOCK, HOLDLOCK) "
                "WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '+505', ''), '+', '') = ? "
                "AND ID <> ? AND ID > 1"
            ),
        )
        if cursor.fetchone():
            conn.rollback()
            return jsonify(error=DUPLICATE_PHONE_MSG), 409

        execute_sp(
            cursor,
            'crm.sp_InsertarClienteRapido',
            (nombre, telefono),
            fallback_sql=(
                "INSERT INTO Clientes (Nombre, Telefono, NivelConfianzaID) "
                "OUTPUT INSERTED.ID VALUES (?, ?, 1)"
            ),
        )
        row = cursor.fetchone()
        new_id = int(row[0]) if row else None
        if new_id and apellidos:
            execute_sp(
                cursor,
                'crm.sp_ActualizarClienteAdmin',
                (nombre, apellidos, telefono, data.get('genero'), data.get('fecha_nacimiento'), int(data.get('nivel_id') or 1), new_id),
                fallback_sql=(
                    "UPDATE Clientes SET Nombre=?, Apellidos=?, Telefono=?, Genero=?, "
                    "FechaNacimiento=?, NivelConfianzaID=? WHERE ID=? AND ID > 1"
                ),
            )
        conn.commit()
        return jsonify(status='success', id=new_id, telefono=telefono, mensaje='Cliente creado.'), 201
    except ValueError as exc:
        conn.rollback()
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        conn.rollback()
        if _is_duplicate_phone_error(exc):
            return jsonify(error=DUPLICATE_PHONE_MSG), 409
        raise
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
    telefono = normalize_customer_phone(data.get('telefono'))
    nivel_id = data.get('nivel_id')
    if nivel_id is None:
        raise ValueError('Seleccione un nivel de fidelidad.')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'crm.sp_VerificarTelefonoClienteDuplicado',
            (telefono, cliente_id),
            fallback_sql=(
                "SELECT ID FROM Clientes WITH (UPDLOCK, HOLDLOCK) "
                "WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '+505', ''), '+', '') = ? "
                "AND ID <> ? AND ID > 1"
            ),
        )
        if cursor.fetchone():
            conn.rollback()
            return jsonify(error=DUPLICATE_PHONE_MSG), 409
        execute_sp(
            cursor,
            'crm.sp_VerificarNivelConfianzaExiste',
            (int(nivel_id),),
            fallback_sql="SELECT ID FROM NivelesConfianza WHERE ID = ?",
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify(error='Nivel de fidelidad inexistente.'), 400
        execute_sp(
            cursor,
            'crm.sp_ActualizarClienteAdmin',
            (nombre, apellidos, telefono, data.get('genero'), data.get('fecha_nacimiento'), int(nivel_id), cliente_id),
            fallback_sql=(
                "UPDATE Clientes SET Nombre=?, Apellidos=?, Telefono=?, Genero=?, "
                "FechaNacimiento=?, NivelConfianzaID=? WHERE ID=? AND ID > 1"
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify(error='Cliente no encontrado.'), 404
        conn.commit()
        return jsonify(status='success', telefono=telefono, mensaje='Cliente actualizado.')
    except Exception as exc:
        conn.rollback()
        if _is_duplicate_phone_error(exc):
            return jsonify(error=DUPLICATE_PHONE_MSG), 409
        raise
    finally:
        conn.close()
