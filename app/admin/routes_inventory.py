from app.services.validation import amount, positive_int, required_text
# app/admin/routes_inventory.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
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
    cursor.execute(
        "SELECT m.ID, m.Nombre, u.Nombre AS Unidad, m.StockActual, m.StockMinimo "
        "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY m.Nombre"
    )
    materias = [{'id': r.ID, 'nombre': r.Nombre, 'unidad': r.Unidad, 'stock': float(r.StockActual), 'minimo': float(r.StockMinimo)} for r in cursor.fetchall()]

    # Proveedores
    cursor.execute("SELECT ID, Nombre, Telefono FROM Proveedores WHERE Activo = 1 ORDER BY Nombre")
    proveedores = [{'id': r.ID, 'nombre': r.Nombre, 'telefono': r.Telefono or ''} for r in cursor.fetchall()]

    # Unidades de Medida
    cursor.execute("SELECT ID, Nombre, Abreviatura FROM UnidadesMedida ORDER BY Nombre")
    unidades = [{'id': r.ID, 'nombre': r.Nombre, 'abreviatura': r.Abreviatura} for r in cursor.fetchall()]

    # Historial de Compras (Últimas 50)
    cursor.execute(
        "SELECT TOP 50 c.ID, m.Nombre AS Materia, p.Nombre AS Proveedor, c.Cantidad, c.CostoTotal, c.Fecha "
        "FROM ComprasMateriaPrima c "
        "JOIN MateriaPrima m ON c.MateriaPrimaID = m.ID "
        "JOIN Proveedores p ON c.ProveedorID = p.ID "
        "ORDER BY c.Fecha DESC"
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
        cursor.execute(
            "INSERT INTO MateriaPrima (Nombre, UnidadMedidaID, StockMinimo, StockActual) OUTPUT INSERTED.ID VALUES (?, ?, ?, 0.0)",
            datos.get('nombre'), int(datos.get('unidad_id')), amount(datos.get('stock_minimo'), 'Stock mínimo')
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Materia prima creada con éxito', 'id': new_id})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
        cursor.execute('SELECT ID FROM UnidadesMedida WHERE ID=?', unidad_id)
        if not cursor.fetchone():
            return jsonify(error='Unidad de medida inexistente.'), 400
        cursor.execute(
            'UPDATE MateriaPrima SET Nombre=?, UnidadMedidaID=?, StockMinimo=? WHERE ID=?',
            nombre, unidad_id, stock_minimo, materia_id
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
        cursor.execute(
            "INSERT INTO Proveedores (Nombre, Telefono) OUTPUT INSERTED.ID VALUES (?, ?)",
            datos.get('nombre'), datos.get('telefono', '')
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Proveedor creado con éxito', 'id': new_id})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
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
        cursor.execute('UPDATE Proveedores SET Nombre=?, Telefono=? WHERE ID=? AND Activo=1', nombre, telefono, proveedor_id)
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
        cursor.execute('INSERT INTO UnidadesMedida (Nombre, Abreviatura) OUTPUT INSERTED.ID VALUES (?, ?)', nombre, abreviatura)
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
        
    cantidad=amount(datos.get('cantidad'), 'Cantidad', minimum=0.01)
    monto_total=amount(datos.get('costo'), 'Costo', minimum=0.01)
    iva=amount(datos.get('iva_documentado',0), 'IVA documentado', maximum=monto_total)
    factura_proveedor=(datos.get('factura_proveedor') or '').strip()
    if not factura_proveedor:
        return jsonify(error='Registre el número del comprobante del proveedor.'),400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.fiscal_service import configuration
        cursor.execute('SELECT ID FROM MateriaPrima WITH (UPDLOCK, HOLDLOCK) WHERE ID=?', int(datos.get('materia_id')))
        if not cursor.fetchone():
            return jsonify(error='Materia prima inexistente.'), 400
        cursor.execute('SELECT ID FROM Proveedores WHERE ID=? AND Activo=1', int(datos.get('proveedor_id')))
        if not cursor.fetchone():
            return jsonify(error='Proveedor inexistente o inactivo.'), 400
        if iva and configuration(cursor).get('fiscal_regimen') != 'General':
            return jsonify(error='El crédito de IVA requiere régimen general y soporte fiscal válido.'),400
        # Registrar compra
        monto_sin_iva = monto_total - iva
        purchased_at = business_now()
        
        cursor.execute(
            "INSERT INTO ComprasMateriaPrima (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha) OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, ?, ?, ?)",
            int(datos.get('materia_id')), int(datos.get('proveedor_id')), cantidad, monto_total, factura_proveedor, iva, purchased_at
        )
        new_id = cursor.fetchone()[0]
        
        # Sumar stock
        cursor.execute(
            "UPDATE MateriaPrima SET StockActual = StockActual + ? WHERE ID = ?",
            cantidad, int(datos.get('materia_id'))
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
            metodo_pago='Credito', # Por defecto a crédito (CxP)
            fecha=purchased_at,
            ip=request.remote_addr
        )
        # ============================================================
        
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Compra registrada y contabilizada con éxito', 'id': new_id})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)),400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


# ============================================================
# MÓDULO DE PRODUCCIÓN Y RECETAS
# ============================================================


