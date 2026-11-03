from app.services.validation import amount, positive_int, required_text, validate_telefono_nicaragua
# app/admin/routes_inventory.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import re
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.services.business_time import business_now
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime


_DUMMY_RUCS = {'NA', 'N/A', 'SINRUC', 'NINGUNO', 'NULL', 'NONE', 'CONSUMIDORFINAL', 'CF', '0'}
_DUMMY_INVOICES = {'S/N', 'SN', 'N/A', 'NA', 'SIN FACTURA', 'SINFACTURA', 'NINGUNA', 'NULL', 'NONE', '0', '-'}


def _validate_supplier_ruc(raw_ruc: str | None) -> str | None:
    """Valida y normaliza el RUC de un proveedor para soporte fiscal de crédito de IVA."""
    if raw_ruc is None:
        return None
    cleaned = re.sub(r'[\s\-]+', '', str(raw_ruc).strip().upper())
    if not cleaned or cleaned in _DUMMY_RUCS:
        return None
    if not re.fullmatch(r'[A-Z0-9]{10,20}', cleaned):
        return None
    digit_count = sum(1 for ch in cleaned if ch.isdigit())
    if digit_count < 6:
        return None
    if len(set(cleaned)) <= 1:
        return None
    return cleaned


def _validate_supplier_invoice(raw_invoice: str | None) -> str | None:
    """Valida que el número de factura del proveedor sea un comprobante válido."""
    if raw_invoice is None:
        return None
    cleaned = str(raw_invoice).strip()
    if not cleaned or cleaned.upper() in _DUMMY_INVOICES:
        return None
    alnum = re.sub(r'[^A-Za-z0-9]', '', cleaned)
    if len(alnum) < 2:
        return None
    return cleaned[:100]


@admin_bp.route('/inventario')
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def inventario():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Materia Prima
    execute_sp(
        cursor,
        'produccion.sp_ListarInventarioMateriasPrimas',
        fallback_sql=(
            "SELECT m.ID, m.Nombre, u.Nombre AS Unidad, m.StockActual, m.StockMinimo "
            "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
            "ORDER BY m.Nombre"
        ),
    )
    materias = [{'id': r.ID, 'nombre': r.Nombre, 'unidad': r.Unidad, 'stock': float(r.StockActual), 'minimo': float(r.StockMinimo)} for r in cursor.fetchall()]

    # Proveedores
    execute_sp(
        cursor,
        'produccion.sp_ListarProveedoresActivos',
        fallback_sql="SELECT ID, Nombre, Telefono FROM Proveedores WHERE Activo = 1 ORDER BY Nombre",
    )
    proveedores = [
        {
            'id': r.ID,
            'nombre': r.Nombre,
            'telefono': r.Telefono or '',
            'ruc': getattr(r, 'RUC', None) or (r[3] if len(r) > 3 else '') or '',
        }
        for r in cursor.fetchall()
    ]

    # Unidades de Medida
    execute_sp(
        cursor,
        'produccion.sp_ListarUnidadesMedida',
        fallback_sql="SELECT ID, Nombre, Abreviatura FROM UnidadesMedida ORDER BY Nombre",
    )
    unidades = [{'id': r.ID, 'nombre': r.Nombre, 'abreviatura': r.Abreviatura} for r in cursor.fetchall()]

    # Historial de Compras (Últimas 50)
    execute_sp(
        cursor,
        'produccion.sp_ListarUltimasComprasMP',
        fallback_sql=(
            "SELECT TOP 50 c.ID, m.Nombre AS Materia, p.Nombre AS Proveedor, c.Cantidad, c.CostoTotal, c.Fecha "
            "FROM ComprasMateriaPrima c "
            "JOIN MateriaPrima m ON c.MateriaPrimaID = m.ID "
            "JOIN Proveedores p ON c.ProveedorID = p.ID "
            "ORDER BY c.Fecha DESC"
        ),
    )
    compras = [{'id': r.ID, 'materia': r.Materia, 'proveedor': r.Proveedor, 'cantidad': float(r.Cantidad), 'costo': float(r.CostoTotal), 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/inventario.html', user=current_user, materias=materias, proveedores=proveedores, unidades=unidades, compras=compras)


@admin_bp.route('/api/inventario/materia_prima', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_materia_prima():
    datos = request.json
    if not datos.get('nombre') or not datos.get('unidad_id') or datos.get('stock_minimo') is None:
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_CrearMateriaPrima',
            (datos.get('nombre'), int(datos.get('unidad_id')), amount(datos.get('stock_minimo'), 'Stock mínimo')),
            fallback_sql="INSERT INTO MateriaPrima (Nombre, UnidadMedidaID, StockMinimo, StockActual) OUTPUT INSERTED.ID VALUES (?, ?, ?, 0.0)",
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Materia prima creada con éxito', 'id': new_id})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/inventario/materia_prima/<int:materia_id>', methods=['PUT'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def editar_materia_prima(materia_id):
    data = request.get_json(silent=True) or {}
    nombre = required_text(data.get('nombre'), 'Nombre', 100)
    unidad_id = positive_int(data.get('unidad_id'), 'Unidad')
    stock_minimo = amount(data.get('stock_minimo'), 'Stock mínimo')
    raw_factor = (
        data.get('factor_conversion')
        if data.get('factor_conversion') is not None
        else (data.get('conversion_factor') if data.get('conversion_factor') is not None else data.get('factor'))
    )
    factor_conversion = None
    if raw_factor is not None and str(raw_factor).strip() != '':
        factor_conversion = float(amount(raw_factor, 'Factor de conversión', minimum=0.000001, maximum=1000000))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_VerificarUnidadMedidaExiste',
            (unidad_id,),
            fallback_sql='SELECT ID FROM UnidadesMedida WHERE ID=?',
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify(error='Unidad de medida inexistente.'), 400

        execute_sp(
            cursor,
            'produccion.sp_ObtenerEstadoMateriaPrimaParaEdicion',
            (materia_id,),
            fallback_sql=(
                "SELECT m.ID, m.Nombre, m.UnidadMedidaID, m.StockActual, m.StockMinimo, "
                "ISNULL(m.CostoUnitario, 0) AS CostoUnitario, "
                "(SELECT COUNT(*) FROM RecetaProducto r WHERE r.MateriaPrimaID = m.ID) AS TotalRecetas, "
                "(SELECT COUNT(*) FROM ComprasMateriaPrima c WHERE c.MateriaPrimaID = m.ID) AS TotalCompras, "
                "(SELECT COUNT(*) FROM ConsumoLote cl WHERE cl.MateriaPrimaID = m.ID) AS TotalConsumos "
                "FROM MateriaPrima m WITH (UPDLOCK, HOLDLOCK) WHERE m.ID = ?"
            ),
        )
        estado_row = cursor.fetchone()
        if not estado_row:
            conn.rollback()
            return jsonify(error='Materia prima no encontrada.'), 404

        unidad_actual_id = getattr(estado_row, 'UnidadMedidaID', estado_row[2] if len(estado_row) > 2 else None)
        stock_actual = float(getattr(estado_row, 'StockActual', estado_row[3] if len(estado_row) > 3 else 0) or 0)
        total_recetas = int(getattr(estado_row, 'TotalRecetas', estado_row[6] if len(estado_row) > 6 else 0) or 0)
        total_compras = int(getattr(estado_row, 'TotalCompras', estado_row[7] if len(estado_row) > 7 else 0) or 0)
        total_consumos = int(getattr(estado_row, 'TotalConsumos', estado_row[8] if len(estado_row) > 8 else 0) or 0)

        if unidad_actual_id is not None and int(unidad_id) != int(unidad_actual_id):
            tiene_dependencias = (stock_actual > 0 or total_recetas > 0 or total_compras > 0 or total_consumos > 0)
            if tiene_dependencias and (factor_conversion is None or factor_conversion <= 0):
                conn.rollback()
                return jsonify(
                    error=(
                        'No se puede cambiar la unidad de medida de un insumo con existencias, '
                        'recetas o movimientos asociados sin proporcionar un factor de conversión válido (factor_conversion > 0).'
                    )
                ), 400

        execute_sp(
            cursor,
            'produccion.sp_ActualizarMateriaPrima',
            (nombre, unidad_id, stock_minimo, materia_id, factor_conversion, getattr(current_user, 'id', None)),
            fallback_sql='UPDATE MateriaPrima SET Nombre=?, UnidadMedidaID=?, StockMinimo=? WHERE ID=?',
            fallback_params=(nombre, unidad_id, stock_minimo, materia_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify(error='Materia prima no encontrada.'), 404
        conn.commit()
        return jsonify(status='success', mensaje='Materia prima actualizada.')
    except Exception as exc:
        conn.rollback()
        msg = str(exc or '').lower()
        if '52025' in msg or '52040' in msg or 'unidad de medida' in msg or 'factor de conversión' in msg or 'factor_conversion' in msg:
            return jsonify(error=str(exc)), 400
        raise
    finally:
        conn.close()


@admin_bp.route('/api/inventario/proveedor', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_proveedor():
    datos = request.json or {}
    if not datos.get('nombre'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    raw_ruc = datos.get('ruc') if datos.get('ruc') is not None else datos.get('RUC')
    validated_ruc = None
    if raw_ruc is not None and str(raw_ruc).strip() != '':
        validated_ruc = _validate_supplier_ruc(raw_ruc)
        if not validated_ruc:
            return jsonify({'error': 'El formato del RUC del proveedor es inválido.'}), 400

    telefono_val = ''
    if datos.get('telefono'):
        try:
            telefono_val = validate_telefono_nicaragua(datos.get('telefono'), 'Teléfono del proveedor', optional=True) or ''
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_CrearProveedor',
            (datos.get('nombre'), telefono_val, validated_ruc),
            fallback_sql="INSERT INTO Proveedores (Nombre, Telefono) OUTPUT INSERTED.ID VALUES (?, ?)",
            fallback_params=(datos.get('nombre'), telefono_val),
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Proveedor creado con éxito', 'id': new_id, 'ruc': validated_ruc})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/inventario/proveedor/<int:proveedor_id>', methods=['PUT'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def editar_proveedor(proveedor_id):
    data = request.get_json(silent=True) or {}
    nombre = required_text(data.get('nombre'), 'Nombre', 150)
    raw_tel = (data.get('telefono') or '').strip()
    telefono = ''
    if raw_tel:
        try:
            telefono = validate_telefono_nicaragua(raw_tel, 'Teléfono del proveedor', optional=True) or ''
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    raw_ruc = data.get('ruc') if data.get('ruc') is not None else data.get('RUC')
    validated_ruc = None
    if raw_ruc is not None and str(raw_ruc).strip() != '':
        validated_ruc = _validate_supplier_ruc(raw_ruc)
        if not validated_ruc:
            return jsonify(error='El formato del RUC del proveedor es inválido.'), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_ActualizarProveedorActivo',
            (nombre, telefono, proveedor_id, validated_ruc),
            fallback_sql='UPDATE Proveedores SET Nombre=?, Telefono=? WHERE ID=? AND Activo=1',
            fallback_params=(nombre, telefono, proveedor_id),
        )
        if cursor.rowcount != 1:
            return jsonify(error='Proveedor no encontrado.'), 404
        conn.commit()
        return jsonify(status='success', mensaje='Proveedor actualizado.', ruc=validated_ruc)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@admin_bp.route('/api/inventario/unidad', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_unidad_medida():
    data = request.get_json(silent=True) or {}
    nombre = required_text(data.get('nombre'), 'Nombre', 50)
    abreviatura = required_text(data.get('abreviatura'), 'Abreviatura', 10)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_CrearUnidadMedida',
            (nombre, abreviatura),
            fallback_sql='INSERT INTO UnidadesMedida (Nombre, Abreviatura) OUTPUT INSERTED.ID VALUES (?, ?)',
        )
        unit_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify(status='success', id=unit_id, mensaje='Unidad creada.'), 201
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@admin_bp.route('/api/inventario/compra', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def registrar_compra():
    datos = request.json or {}
    if not all([datos.get('materia_id'), datos.get('proveedor_id'), datos.get('cantidad'), datos.get('costo')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    materia_id = int(datos.get('materia_id'))
    proveedor_id = int(datos.get('proveedor_id'))
    cantidad = amount(datos.get('cantidad'), 'Cantidad', minimum=0.01)
    monto_total = amount(datos.get('costo'), 'Costo', minimum=0.01)
    iva = amount(datos.get('iva_documentado', 0), 'IVA documentado', maximum=monto_total)
    factura_proveedor = _validate_supplier_invoice(datos.get('factura_proveedor'))
    if not factura_proveedor:
        return jsonify(error='Registre un número de factura o comprobante válido del proveedor.'), 400

    raw_idem = (
        datos.get('idempotency_key')
        or datos.get('request_id')
        or datos.get('clave_solicitud')
        or datos.get('idempotencia')
        or request.headers.get('Idempotency-Key')
        or request.headers.get('X-Idempotency-Key')
    )
    if raw_idem is not None and str(raw_idem).strip():
        idem_key = str(raw_idem).strip()[:100]
    else:
        idem_key = f"FAC:{proveedor_id}:{factura_proveedor.upper()}"[:100]

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.fiscal_service import configuration
        execute_sp(
            cursor,
            'produccion.sp_ObtenerMateriaPrimaBloqueo',
            (materia_id,),
            fallback_sql='SELECT ID FROM MateriaPrima WITH (UPDLOCK, HOLDLOCK) WHERE ID=?',
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify(error='Materia prima inexistente.'), 400

        execute_sp(
            cursor,
            'produccion.sp_VerificarProveedorActivo',
            (proveedor_id,),
            fallback_sql='SELECT ID, Nombre, Telefono, RUC FROM Proveedores WHERE ID=? AND Activo=1',
        )
        prov_row = cursor.fetchone()
        if not prov_row:
            conn.rollback()
            return jsonify(error='Proveedor inexistente o inactivo.'), 400

        raw_req_ruc = (
            datos.get('proveedor_ruc')
            or datos.get('ruc_proveedor')
            or datos.get('ProveedorRUC')
            or datos.get('ruc')
            or datos.get('RUC')
        )
        db_prov_ruc = getattr(prov_row, 'RUC', None) if hasattr(prov_row, 'RUC') else (prov_row[3] if len(prov_row) > 3 else None)
        candidate_ruc = raw_req_ruc if (raw_req_ruc is not None and str(raw_req_ruc).strip() != '') else db_prov_ruc
        validated_ruc = _validate_supplier_ruc(candidate_ruc)

        if iva > 0:
            if configuration(cursor).get('fiscal_regimen') != 'General':
                conn.rollback()
                return jsonify(error='El crédito de IVA requiere régimen general y soporte fiscal válido.'), 400
            if not validated_ruc:
                conn.rollback()
                return jsonify(
                    error='Para acreditar IVA se requiere un proveedor con número RUC válido y factura fiscal.'
                ), 400

        # Verificación de idempotencia bajo bloqueo antes de tocar stock o contabilidad
        execute_sp(
            cursor,
            'produccion.sp_ObtenerCompraPorIdempotencia',
            (idem_key, proveedor_id, factura_proveedor),
            fallback_sql=(
                "SELECT TOP 1 ID, MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, "
                "FacturaProveedor, IVADocumentado, IdempotencyKey "
                "FROM ComprasMateriaPrima WITH (UPDLOCK, HOLDLOCK) "
                "WHERE IdempotencyKey = ? OR (ProveedorID = ? AND UPPER(LTRIM(RTRIM(FacturaProveedor))) = UPPER(LTRIM(RTRIM(?))))"
            ),
        )
        existing = cursor.fetchone()
        if existing:
            existing_id = int(getattr(existing, 'ID', existing[0]))
            existing_mp = int(getattr(existing, 'MateriaPrimaID', existing[1]))
            existing_prov = int(getattr(existing, 'ProveedorID', existing[2]))
            existing_cant = float(getattr(existing, 'Cantidad', existing[3]))
            existing_costo = float(getattr(existing, 'CostoTotal', existing[4]))
            existing_iva = float(getattr(existing, 'IVADocumentado', existing[6] if len(existing) > 6 else 0) or 0)
            same_params = (
                existing_mp == materia_id
                and existing_prov == proveedor_id
                and abs(existing_cant - float(cantidad)) <= 0.0001
                and abs(existing_costo - float(monto_total)) <= 0.01
                and abs(existing_iva - float(iva)) <= 0.01
            )
            if same_params:
                conn.commit()
                return jsonify({
                    'status': 'success',
                    'mensaje': 'Compra registrada y contabilizada con éxito',
                    'id': existing_id,
                    'idempotent': True,
                }), 200
            conn.rollback()
            return jsonify({
                'error': 'La clave de idempotencia o comprobante del proveedor ya fue registrado con parámetros distintos.'
            }), 409

        # Registrar compra
        monto_sin_iva = monto_total - iva
        purchased_at = business_now()

        execute_sp(
            cursor,
            'produccion.sp_InsertarCompraMateriaPrima',
            (materia_id, proveedor_id, cantidad, monto_total, factura_proveedor, iva, purchased_at, idem_key, validated_ruc),
            fallback_sql=(
                "INSERT INTO ComprasMateriaPrima "
                "(MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha) "
                "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            fallback_params=(materia_id, proveedor_id, cantidad, monto_total, factura_proveedor, iva, purchased_at),
        )
        inserted_row = cursor.fetchone()
        new_id = int(inserted_row[0])
        ya_existia = bool(getattr(inserted_row, 'YaExistia', inserted_row[1] if len(inserted_row) > 1 else 0))
        if ya_existia:
            conn.commit()
            return jsonify({
                'status': 'success',
                'mensaje': 'Compra registrada y contabilizada con éxito',
                'id': new_id,
                'idempotent': True,
            }), 200

        # Sumar stock
        execute_sp(
            cursor,
            'produccion.sp_SumarStockMateriaPrima',
            (cantidad, materia_id),
            fallback_sql="UPDATE MateriaPrima SET StockActual = StockActual + ? WHERE ID = ?",
        )
        if cursor.rowcount != 1:
            raise ValueError('No se pudo actualizar el inventario.')

        # ============================================================
        # INTEGRACIÓN CONTABLE NIIF
        # ============================================================
        from app.services.contabilidad_service import ContabilidadService
        ContabilidadService.contabilizar_compra(
            cursor=cursor,
            usuario_id=current_user.id,
            compra_id=new_id,
            referencia=factura_proveedor,
            monto_sin_iva=monto_sin_iva,
            iva=iva,
            monto_total=monto_total,
            metodo_pago='Credito',  # Por defecto a crédito (CxP)
            fecha=purchased_at,
            ip=request.remote_addr
        )
        # ============================================================

        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Compra registrada y contabilizada con éxito', 'id': new_id, 'idempotent': False})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        msg = str(e or '').lower()
        if '52028' in msg or '52029' in msg or 'ruc' in msg or 'soporte fiscal' in msg or 'factura' in msg:
            return jsonify(error=str(e)), 400
        if '2601' in msg or '2627' in msg or 'ux_comprasmateriaprima_idempotencykey' in msg:
            return jsonify(error='Operación duplicada detectada por clave de idempotencia.'), 409
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()
