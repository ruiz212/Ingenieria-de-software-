from app.services.validation import amount, positive_int, required_text
# app/admin/routes_inventory.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.services.business_time import business_now
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

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
    proveedores = [{'id': r.ID, 'nombre': r.Nombre, 'telefono': r.Telefono or ''} for r in cursor.fetchall()]

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
            return jsonify(error='Unidad de medida inexistente.'), 400
        execute_sp(
            cursor,
            'produccion.sp_ActualizarMateriaPrima',
            (nombre, unidad_id, stock_minimo, materia_id),
            fallback_sql='UPDATE MateriaPrima SET Nombre=?, UnidadMedidaID=?, StockMinimo=? WHERE ID=?',
        )
        if cursor.rowcount != 1:
            return jsonify(error='Materia prima no encontrada.'), 404
        conn.commit()
        return jsonify(status='success', mensaje='Materia prima actualizada.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@admin_bp.route('/api/inventario/proveedor', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin', 'Operativo')
def crear_proveedor():
    datos = request.json
    if not datos.get('nombre'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_CrearProveedor',
            (datos.get('nombre'), datos.get('telefono', '')),
            fallback_sql="INSERT INTO Proveedores (Nombre, Telefono) OUTPUT INSERTED.ID VALUES (?, ?)",
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Proveedor creado con éxito', 'id': new_id})
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
    telefono = (data.get('telefono') or '').strip()[:30]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'produccion.sp_ActualizarProveedorActivo',
            (nombre, telefono, proveedor_id),
            fallback_sql='UPDATE Proveedores SET Nombre=?, Telefono=? WHERE ID=? AND Activo=1',
        )
        if cursor.rowcount != 1:
            return jsonify(error='Proveedor no encontrado.'), 404
        conn.commit()
        return jsonify(status='success', mensaje='Proveedor actualizado.')
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
    datos = request.json
    if not all([datos.get('materia_id'), datos.get('proveedor_id'), datos.get('cantidad'), datos.get('costo')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    cantidad = amount(datos.get('cantidad'), 'Cantidad', minimum=0.01)
    monto_total = amount(datos.get('costo'), 'Costo', minimum=0.01)
    iva = amount(datos.get('iva_documentado', 0), 'IVA documentado', maximum=monto_total)
    factura_proveedor = (datos.get('factura_proveedor') or '').strip()
    if not factura_proveedor:
        return jsonify(error='Registre el número del comprobante del proveedor.'), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.fiscal_service import configuration
        execute_sp(
            cursor,
            'produccion.sp_ObtenerMateriaPrimaBloqueo',
            (int(datos.get('materia_id')),),
            fallback_sql='SELECT ID FROM MateriaPrima WITH (UPDLOCK, HOLDLOCK) WHERE ID=?',
        )
        if not cursor.fetchone():
            return jsonify(error='Materia prima inexistente.'), 400
        execute_sp(
            cursor,
            'produccion.sp_VerificarProveedorActivo',
            (int(datos.get('proveedor_id')),),
            fallback_sql='SELECT ID FROM Proveedores WHERE ID=? AND Activo=1',
        )
        if not cursor.fetchone():
            return jsonify(error='Proveedor inexistente o inactivo.'), 400
        if iva and configuration(cursor).get('fiscal_regimen') != 'General':
            return jsonify(error='El crédito de IVA requiere régimen general y soporte fiscal válido.'), 400
        # Registrar compra
        monto_sin_iva = monto_total - iva
        purchased_at = business_now()
        
        execute_sp(
            cursor,
            'produccion.sp_InsertarCompraMateriaPrima',
            (int(datos.get('materia_id')), int(datos.get('proveedor_id')), cantidad, monto_total, factura_proveedor, iva, purchased_at),
            fallback_sql="INSERT INTO ComprasMateriaPrima (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha) OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        new_id = cursor.fetchone()[0]
        
        # Sumar stock
        execute_sp(
            cursor,
            'produccion.sp_SumarStockMateriaPrima',
            (cantidad, int(datos.get('materia_id'))),
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
        return jsonify({'status': 'success', 'mensaje': 'Compra registrada y contabilizada con éxito', 'id': new_id})
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
