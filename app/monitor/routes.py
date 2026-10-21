# app/monitor/routes.py
# Rutas del Monitor de Producción y Seguimiento Público de Encargos

import json
from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user

from app.monitor import monitor_bp
from app.db import get_db_connection, execute_sp, is_sqlserver_cursor
from app.extensions import csrf
from app.auth.decorators import roles_required


def _tiene_columna_estado_fiscal(cursor):
    """Verifica si la columna EstadoFiscal existe en la tabla Facturas de forma compatible."""
    try:
        execute_sp(
            cursor,
            'ventas.sp_VerificarColumnaEstadoFiscalFacturas',
            fallback_sql="SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Facturas' AND COLUMN_NAME = 'EstadoFiscal'",
        )
        return cursor.fetchone() is not None
    except Exception:
        return False


# ============================================================
# SEGUIMIENTO PÚBLICO DE ENCARGOS (sin login)
# ============================================================

@monitor_bp.route('/seguimiento/<codigo>')
def seguimiento(codigo):
    """Página pública para que el cliente vea el estado de su encargo."""
    conn = get_db_connection()
    cursor = conn.cursor()

    condicion_fiscal = "(f.EstadoFiscal IS NULL OR f.EstadoFiscal != 'Anulada') AND " if _tiene_columna_estado_fiscal(cursor) else ""

    execute_sp(
        cursor,
        'ventas.sp_SeguimientoEncargoPublico',
        (codigo,),
        fallback_sql=(
            f"SELECT f.NumeroFactura, f.FechaHora, f.Total, f.Subtotal, f.IVA, "
            f"       e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones, e.RutaImagenReferencia, "
            f"       c.Nombre AS NombreCliente "
            f"FROM Facturas f "
            f"JOIN Encargos e ON e.FacturaID = f.ID "
            f"LEFT JOIN Clientes c ON f.ClienteID = c.ID "
            f"WHERE {condicion_fiscal}f.CodigoSeguimiento = ?"
        ),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return render_template('seguimiento.html', factura=None, codigo=codigo)

    # Obtener el adelanto (suma de pagos realizados hasta el momento)
    execute_sp(
        cursor,
        'ventas.sp_SeguimientoAdelantoPublico',
        (codigo,),
        fallback_sql=(
            "SELECT ISNULL(SUM(Monto), 0) FROM Pagos "
            "WHERE FacturaID = (SELECT ID FROM Facturas WHERE CodigoSeguimiento = ?)"
        ),
    )
    adelanto_row = cursor.fetchone()
    adelanto = float(adelanto_row[0]) if adelanto_row and adelanto_row[0] is not None else 0.0
    saldo = max(0.0, float(row.Total) - adelanto)

    # Obtener productos del encargo
    execute_sp(
        cursor,
        'ventas.sp_SeguimientoProductosPublico',
        (codigo,),
        fallback_sql=(
            f"SELECT ISNULL(p.Nombre, 'Producto') AS Nombre, df.Cantidad, df.PrecioUnitario, df.Subtotal "
            f"FROM DetalleFacturas df "
            f"LEFT JOIN Productos p ON df.ProductoID = p.ID "
            f"JOIN Facturas f ON df.FacturaID = f.ID "
            f"WHERE {condicion_fiscal}f.CodigoSeguimiento = ?"
        ),
    )
    productos = [
        {'nombre': r.Nombre or 'Producto', 'cantidad': r.Cantidad,
         'precio': float(r.PrecioUnitario), 'subtotal': float(r.Subtotal)}
        for r in cursor.fetchall()
    ]
    conn.close()

    fecha_str = row.FechaHora.strftime('%d/%m/%Y') if row.FechaHora else ''
    hora_str = row.FechaHora.strftime('%H:%M:%S') if row.FechaHora else ''
    fecha_entrega_str = row.FechaEntrega.strftime('%d/%m/%Y') if row.FechaEntrega else ''

    factura = {
        'numero_factura': row.NumeroFactura,
        'fecha': fecha_str,
        'hora': hora_str,
        'total': float(row.Total),
        'subtotal': float(row.Subtotal),
        'iva': float(row.IVA),
        'productos': productos,
        'es_encargo': True,
        'encargo_detalles': {
            'estado': row.Estado or 'Pendiente',
            'fecha_entrega': fecha_entrega_str,
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

def cargar_encargos(cursor):
    condicion_fiscal = "(f.EstadoFiscal IS NULL OR f.EstadoFiscal != 'Anulada') AND " if _tiene_columna_estado_fiscal(cursor) else ""
    execute_sp(
        cursor,
        'produccion.sp_MonitorEncargosActivos',
        fallback_sql=(
            f"SELECT f.ID, f.NumeroFactura, f.CodigoSeguimiento, f.FechaHora, f.Total, "
            f"       e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones, e.RutaImagenReferencia, e.TelefonoContacto, "
            f"       c.Nombre AS ClienteNombre, c.Telefono AS ClienteTelefono "
            f"FROM Facturas f "
            f"JOIN Encargos e ON e.FacturaID = f.ID "
            f"LEFT JOIN Clientes c ON f.ClienteID = c.ID "
            f"WHERE {condicion_fiscal}e.Estado != 'Entregado' "
            f"ORDER BY e.FechaEntrega ASC"
        ),
    )
    rows = cursor.fetchall()
    factura_ids = [row.ID for row in rows]
    detalles_por_factura = {factura_id: [] for factura_id in factura_ids}
    if factura_ids:
        placeholders = ','.join('?' for _ in factura_ids)
        detail_params = (json.dumps(factura_ids),) if is_sqlserver_cursor(cursor) else factura_ids
        execute_sp(
            cursor,
            'produccion.sp_MonitorDetallesEncargosActivos',
            detail_params,
            fallback_sql=(
                f"SELECT df.ID, df.FacturaID, ISNULL(p.Nombre, 'Producto') AS Nombre, df.Cantidad, df.PrecioUnitario, "
                f"i.ID AS IngredienteID, i.Nombre AS IngredienteNombre "
                f"FROM DetalleFacturas df "
                f"LEFT JOIN Productos p ON p.ID=df.ProductoID "
                f"LEFT JOIN DetalleIngredientes di ON di.DetalleFacturaID=df.ID "
                f"LEFT JOIN Ingredientes i ON i.ID=di.IngredienteID "
                f"WHERE df.FacturaID IN ({placeholders}) ORDER BY df.ID, i.Nombre"
            ),
        )
        detalles = {}
        for detail in cursor.fetchall():
            item = detalles.setdefault(detail.ID, {
                'id': detail.ID,
                'factura_id': detail.FacturaID,
                'nombre': detail.Nombre or 'Producto',
                'cantidad': detail.Cantidad,
                'precio': float(detail.PrecioUnitario),
                'detalle_ingredientes': {'ingredientes': []}
            })
            if detail.IngredienteID:
                item['detalle_ingredientes']['ingredientes'].append({
                    'id': detail.IngredienteID,
                    'nombre': detail.IngredienteNombre
                })
        for item in detalles.values():
            factura_id = item.pop('factura_id')
            detalles_por_factura[factura_id].append(item)

    encargos = []
    for row in rows:
        fecha_str = row.FechaHora.strftime('%d/%m/%Y %H:%M') if row.FechaHora else ''
        hora_str = row.FechaHora.strftime('%H:%M') if row.FechaHora else ''
        fecha_entrega_str = row.FechaEntrega.strftime('%d/%m/%Y') if row.FechaEntrega else ''

        encargos.append({
            'numero_factura': row.NumeroFactura,
            'codigo_seguimiento': row.CodigoSeguimiento,
            'fecha': fecha_str,
            'hora': hora_str,
            'productos': detalles_por_factura.get(row.ID, []),
            'total': float(row.Total),
            'es_encargo': True,
            'encargo_detalles': {
                'estado': row.Estado or 'Pendiente',
                'fecha_entrega': fecha_entrega_str,
                'notas': row.NotasCliente or '',
                'especificaciones': row.Especificaciones or '',
                'ruta_imagen_referencia': row.RutaImagenReferencia or '',
                'nombre_cliente': row.ClienteNombre or 'Cliente General',
                'telefono': row.TelefonoContacto or row.ClienteTelefono or ''
            }
        })
    return encargos


@monitor_bp.route('/monitor')
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Operativo')
def monitor_pedidos():
    """Panel interno para que la panadería vea y actualice los pedidos en cocina."""
    conn = get_db_connection()
    try:
        encargos = cargar_encargos(conn.cursor())
    finally:
        conn.close()
    return render_template('monitor.html', encargos=encargos, user=current_user)


@monitor_bp.route('/api/monitor/pedidos')
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Operativo')
def monitor_pedidos_json():
    """API para obtener en tiempo real los encargos activos del monitor."""
    conn = get_db_connection()
    try:
        return jsonify(encargos=cargar_encargos(conn.cursor()))
    finally:
        conn.close()


# ============================================================
# API: ACTUALIZAR ESTADO DE ENCARGO
# ============================================================

@monitor_bp.route('/api/seguimiento/<codigo>/estado', methods=['PUT'])
@login_required
@roles_required('Estandar', 'Admin', 'SuperAdmin', 'Operativo')
def actualizar_estado(codigo):
    """Actualiza el estado de un encargo en la BD (Pendiente, En Proceso, Listo, Entregado)."""
    from app.services.contabilidad_service import ContabilidadService, ContabilidadError
    data = request.get_json() or {}
    nuevo_estado = data.get('estado')

    estados_validos = ['Pendiente', 'En Proceso', 'Listo', 'Entregado']
    if nuevo_estado not in estados_validos:
        return jsonify({'error': 'Estado inválido. Debe ser Pendiente, En Proceso, Listo o Entregado.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_ObtenerEncargoPorCodigoBloqueo',
            (codigo,),
            fallback_sql=(
                "SELECT e.Estado, f.ID, f.NumeroFactura, f.Total, f.EstadoFiscal FROM Facturas f WITH (UPDLOCK, HOLDLOCK) "
                "JOIN Encargos e WITH (UPDLOCK, HOLDLOCK) ON f.ID = e.FacturaID "
                "WHERE f.CodigoSeguimiento = ?"
            ),
        )
        previous = cursor.fetchone()
        if not previous:
            return jsonify(error='Encargo no encontrado.'), 404

        estado_anterior = previous[0]
        factura_id = previous[1]
        numero_factura = previous[2]
        factura_total = previous[3]
        if previous[4] != 'Emitida':
            return jsonify(error='La factura está anulada o requiere revisión fiscal.'), 409

        if nuevo_estado == estado_anterior:
            return jsonify(status='success', nuevo_estado=nuevo_estado)

        # Validate collection policy and lock the receiving shift before changing the order.
        saldo_pendiente = 0
        if nuevo_estado == 'Entregado':
            from app.services.validation import amount
            from app.services.business_time import business_now
            execute_sp(
                cursor,
                'ventas.sp_ObtenerTotalPagadoFactura',
                (factura_id,),
                fallback_sql="SELECT ISNULL(SUM(Monto), 0) FROM Pagos WHERE FacturaID = ?",
            )
            pagado_row = cursor.fetchone()
            pagado = amount(pagado_row[0] if pagado_row and pagado_row[0] is not None else 0)
            saldo_pendiente = amount(factura_total) - pagado
            if saldo_pendiente > 0:
                if getattr(current_user, 'rol_nombre', None) == 'Operativo':
                    conn.rollback()
                    return jsonify(error='El cobro pendiente debe confirmarlo un cajero con turno abierto.'), 409
                execute_sp(
                    cursor, 'ventas.sp_ObtenerTurnoActivoParaVenta', (current_user.id,),
                    fallback_sql='SELECT ID FROM TurnosCaja WITH(UPDLOCK,HOLDLOCK) WHERE UsuarioID = ? AND Cerrado = 0',
                )
                turno_receptor = cursor.fetchone()
                if not turno_receptor:
                    conn.rollback()
                    return jsonify(error='Se requiere un turno de caja abierto para recibir el saldo.'), 409
                turno_receptor_id = turno_receptor[0]
                execute_sp(
                    cursor, 'ventas.sp_VerificarArqueoPendienteTurno', (turno_receptor_id,),
                    fallback_sql="SELECT ID FROM ArqueoCaja WHERE TurnoID=? AND EstadoArqueo IN ('Pendiente','Verificado')",
                )
                if cursor.fetchone():
                    conn.rollback()
                    return jsonify(error='No se puede recibir un cobro durante un arqueo pendiente.'), 409

        execute_sp(
            cursor,
            'produccion.sp_ActualizarEstadoEncargoCompare',
            (nuevo_estado, codigo, estado_anterior),
            fallback_sql=(
                "UPDATE e SET Estado = ? "
                "FROM Encargos AS e JOIN Facturas AS f ON e.FacturaID = f.ID "
                "WHERE f.CodigoSeguimiento = ? AND e.Estado = ? AND f.EstadoFiscal = 'Emitida'"
            ),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({'error': 'No se pudo actualizar el estado del encargo.'}), 409

        if saldo_pendiente > 0:
            metodo_saldo = data.get('metodo_pago', 'Efectivo')
            if metodo_saldo not in ('Efectivo', 'Transferencia', 'Efectivo USD'):
                metodo_saldo = 'Efectivo'
            ref_saldo = data.get('referencia') or 'Liquidación de saldo al entregar'
            now_delivery = business_now()
            from app.services.currency import official_usd_rate
            exchange = official_usd_rate(cursor) if metodo_saldo == 'Efectivo USD' else None
            execute_sp(
                cursor,
                'ventas.sp_InsertarPagoSaldoEncargo',
                (factura_id, metodo_saldo, saldo_pendiente, ref_saldo, now_delivery, exchange, turno_receptor_id, current_user.id),
                fallback_sql=(
                    "INSERT INTO Pagos (FacturaID, MetodoPago, Monto, NombreTransferente, FechaPago, MonedaRegistro, TipoCambioAplicado, TurnoReceptorID, UsuarioReceptorID) "
                    "VALUES (?, ?, ?, ?, ?, 'NIO', ?, ?, ?)"
                ),
            )
            # El pago y la entrega sólo existen si su asiento también se guarda.
            ContabilidadService.contabilizar_cobro_encargo(
                cursor, current_user.id, numero_factura,
                saldo_pendiente, metodo_saldo,
                ip=request.remote_addr, fecha=now_delivery
            )

        # Auditoría fiscal opcional (no interrumpe el flujo si la bitácora no está configurada)
        try:
            from app.services.fiscal_service import audit
            audit(cursor, current_user.id, 'ESTADO_ENCARGO', 'Factura', factura_id,
                  {'antes': estado_anterior, 'despues': nuevo_estado}, request.remote_addr)
        except Exception as audit_err:
            current_app.logger.warning(f"Auditoría BitacoraFiscal omitida para encargo {codigo}: {audit_err}")

        conn.commit()
        return jsonify({
            'status': 'success',
            'mensaje': 'Estado actualizado correctamente',
            'nuevo_estado': nuevo_estado
        }), 200
    except ContabilidadError as error:
        conn.rollback()
        return jsonify(error=f'No se confirmó la entrega ni el cobro: {error}'), 409
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error actualizando encargo')
        return jsonify(error='No se pudo actualizar el encargo.'), 500
    finally:
        conn.close()
