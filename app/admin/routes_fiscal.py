"""Herramientas de control fiscal; la autorización corresponde a la DGI."""
import csv
import io
import json
from datetime import datetime, date
from decimal import Decimal
from flask import render_template, request, jsonify, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.auth.decorators import roles_required
from app.db import get_db_connection, execute_sp
from app.services.business_time import business_now
from app.services.fiscal_service import configuration, audit
from app.services.contabilidad_service import ContabilidadService, ContabilidadError
from app.services.validation import amount, required_text, validate_telefono_nicaragua


@admin_bp.route('/fiscal')
@login_required
@roles_required('Admin','SuperAdmin')
def fiscal():
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        config=configuration(cursor)
        execute_sp(
            cursor,
            'ventas.sp_ListarUltimasFacturasFiscal',
            fallback_sql='SELECT TOP 100 ID,NumeroFactura,FechaHora,Total,EstadoFiscal,DocumentoJSON FROM Facturas ORDER BY ID DESC',
        )
        invoices=[dict(zip([c[0] for c in cursor.description],row)) for row in cursor.fetchall()]
        execute_sp(
            cursor,
            'catalogo.sp_ListarProductosFiscal',
            fallback_sql='SELECT ID,Nombre,TasaIVA,MotivoExencion FROM Productos WHERE Activo=1 ORDER BY Nombre',
        )
        products=cursor.fetchall()
        execute_sp(
            cursor,
            'contabilidad.sp_ListarPeriodosContablesFiscal',
            fallback_sql='SELECT ID,Mes,Anio,Estado FROM PeriodosContables ORDER BY Anio DESC,Mes DESC',
        )
        periods=cursor.fetchall()
        execute_sp(
            cursor,
            'fiscal.sp_ListarEventosBitacoraFiscal',
            (50, None),
            fallback_sql='SELECT TOP 50 ID,Fecha,UsuarioID,Accion,Entidad,EntidadID,Detalle,IP FROM BitacoraFiscal ORDER BY ID DESC',
            fallback_params=(),
        )
        events=cursor.fetchall()
        execute_sp(
            cursor,
            'contabilidad.sp_ListarUltimosAsientosFiscal',
            fallback_sql='SELECT TOP 50 ID,NumeroComprobante,Fecha,Descripcion,Estado FROM AsientosDiario ORDER BY ID DESC',
        )
        entries=cursor.fetchall()
        return render_template('admin/fiscal.html',config=config,invoices=invoices,products=products,periods=periods,events=events,entries=entries)
    finally:
        conn.close()


@admin_bp.route('/fiscal/configuracion',methods=['POST'])
@login_required
@roles_required('Admin','SuperAdmin')
def fiscal_configuration():
    fields=('regimen','razon_social','ruc','direccion','telefono','correo','autorizacion','sucursal')
    data={f'fiscal_{k}':request.form.get(k,'').strip() for k in fields}
    if data['fiscal_regimen'] not in ('Pendiente','Cuota fija','General'):
        raise ValueError('Seleccione un régimen válido.')
    if any(len(v)>255 for v in data.values()):
        raise ValueError('Los datos del emisor admiten hasta 255 caracteres.')
    if data['fiscal_regimen']!='Pendiente':
        for field in ('razon_social','ruc','direccion','telefono','autorizacion'):
            required_text(data['fiscal_'+field],field,255)
    if data.get('fiscal_telefono'):
        data['fiscal_telefono'] = validate_telefono_nicaragua(
            data['fiscal_telefono'],
            'Teléfono del emisor',
            optional=(data['fiscal_regimen'] == 'Pendiente')
        ) or ''
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        old=configuration(cursor)
        for key,value in data.items():
            execute_sp(
                cursor,
                'seguridad.sp_ActualizarConfiguracionClaveValor',
                (value, key),
                fallback_sql='UPDATE ConfiguracionSistema SET Valor=? WHERE Clave=?',
            )
        audit(cursor,current_user.id,'CONFIGURACION','Sistema',None,{'antes':{k:old.get(k) for k in data},'despues':data},request.remote_addr)
        conn.commit()
        flash('Datos guardados. Las facturas anteriores conservan su emisor original.','success')
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return redirect(url_for('admin.fiscal'))


@admin_bp.route('/fiscal/asientos/<int:entry_id>/imprimir')
@login_required
@roles_required('Admin','SuperAdmin')
def print_journal(entry_id):
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        row=execute_sp(
            cursor,
            'contabilidad.sp_ObtenerAsientoDiarioPorID',
            (entry_id,),
            fallback_sql='SELECT * FROM AsientosDiario WHERE ID=?',
        ).fetchone()
        if not row:
            return 'Comprobante no encontrado.',404
        entry=dict(zip([c[0] for c in cursor.description],row))
        emisor=json.loads(entry['EmisorJSON']) if entry.get('EmisorJSON') else {}
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerDetallesAsientoImpresion',
            (entry_id,),
            fallback_sql='SELECT c.Codigo,c.Nombre,d.Descripcion,d.Debe,d.Haber FROM DetalleAsientos d JOIN CatalogoCuentas c ON c.ID=d.CuentaID WHERE d.AsientoID=? ORDER BY d.ID',
        )
        details=cursor.fetchall()
        user_name = entry.get('UsuarioID')
        if entry.get('UsuarioID'):
            try:
                execute_sp(
                    cursor,
                    'seguridad.sp_ObtenerNombreUsuarioPorID',
                    (int(entry['UsuarioID']),),
                    fallback_sql='SELECT NombreCompleto FROM Usuarios WHERE ID = ?',
                )
                u_row = cursor.fetchone()
                if u_row and u_row[0]:
                    user_name = u_row[0]
            except Exception:
                pass
        return render_template('admin/comprobante_imprimir.html',entry=entry,emisor=emisor,details=details,
                               debe=sum(r.Debe for r in details),haber=sum(r.Haber for r in details),
                               user_name=user_name)
    finally:
        conn.close()


@admin_bp.route('/fiscal/productos/<int:product_id>',methods=['POST'])
@login_required
@roles_required('Admin','SuperAdmin')
def fiscal_product(product_id):
    rate=amount(request.form.get('tasa'), 'Tasa IVA',maximum=100)
    if rate not in (Decimal('0'),Decimal('15')):
        raise ValueError('Seleccione 0% o 15%. Confirme el tratamiento aplicable al producto.')
    reason=request.form.get('motivo','').strip()
    if rate==0:
        required_text(reason,'Fundamento de exención o tasa cero',200)
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        execute_sp(
            cursor,
            'catalogo.sp_ActualizarTratamientoIVAProducto',
            (product_id, rate, reason or None),
            fallback_sql='UPDATE Productos SET TasaIVA=?,MotivoExencion=? WHERE ID=?',
            fallback_params=(rate, reason or None, product_id),
        )
        audit(cursor,current_user.id,'TRATAMIENTO_IVA','Producto',product_id,{'tasa':rate,'fundamento':reason},request.remote_addr)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return redirect(url_for('admin.fiscal'))


@admin_bp.route('/fiscal/facturas/<int:invoice_id>/imprimir')
@login_required
@roles_required('Estandar','Admin','SuperAdmin')
def print_invoice(invoice_id):
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        execute_sp(
            cursor,
            'ventas.sp_ObtenerFacturaImpresion',
            (invoice_id,),
            fallback_sql='SELECT DocumentoJSON,EstadoFiscal,MotivoAnulacion FROM Facturas WHERE ID=?',
        )
        row=cursor.fetchone()
        if not row:
            return 'Factura no encontrada',404
        if not row[0]:
            return 'Documento histórico sin copia fiscal guardada. Consulte el soporte original; no se reconstruyen datos fiscales retroactivamente.',409
        try:
            document = json.loads(row[0])
        except (ValueError, TypeError):
            return 'La copia fiscal guardada no se puede interpretar. Consulte el respaldo original.',409
        if not isinstance(document, dict):
            return 'La copia fiscal guardada tiene una estructura inválida. Consulte el respaldo original.',409
        return render_template('admin/factura_imprimir.html',invoice=document,state=row[1],reason=row[2])
    finally:
        conn.close()


@admin_bp.route('/fiscal/facturas/<int:invoice_id>/anular',methods=['POST'])
@login_required
@roles_required('Admin','SuperAdmin')
def void_invoice(invoice_id):
    motivo=required_text(request.form.get('motivo'),'Motivo de anulación',300)
    if len(motivo)<5:
        raise ValueError('Describa el motivo de anulación.')
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        execute_sp(
            cursor,
            'ventas.sp_ObtenerFacturaParaAnularBloqueo',
            (invoice_id,),
            fallback_sql='SELECT EstadoFiscal,DocumentoJSON,TurnoID,ClienteID FROM Facturas WITH (UPDLOCK,HOLDLOCK) WHERE ID=?',
        )
        row=cursor.fetchone()
        if not row or row[0]=='Anulada' or not row[1]:
            raise ValueError('La factura no existe, ya está anulada o requiere revisión histórica.')
        execute_sp(
            cursor,
            'ventas.sp_ObtenerEstadoCerradoTurnoBloqueo',
            (row[2],),
            fallback_sql='SELECT Cerrado FROM TurnosCaja WITH(UPDLOCK,HOLDLOCK) WHERE ID=?',
        )
        shift=cursor.fetchone()
        if not shift or shift[0]:
            raise ValueError('La caja ya está cerrada. La corrección requiere revisión contable y documento de ajuste.')
        execute_sp(
            cursor,
            'ventas.sp_VerificarArqueoPendienteTurno',
            (row[2],),
            fallback_sql="SELECT ID FROM ArqueoCaja WHERE TurnoID=? AND EstadoArqueo IN ('Pendiente','Verificado')",
        )
        if cursor.fetchone():
            raise ValueError('No se puede anular durante un arqueo pendiente.')
        doc=json.loads(row[1])
        voided_at=business_now()
        ContabilidadService.revertir_asiento(cursor,doc['asiento_id'],current_user.id,motivo,request.remote_addr,fecha=voided_at)
        if doc.get('numero_factura'):
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerAsientosSaldoEncargoActivos',
                (f"SALDO-{doc['numero_factura']}",),
                fallback_sql="SELECT ID FROM AsientosDiario WHERE ReferenciaExterna=? AND Estado='Contabilizado'",
            )
            for saldo_asiento in cursor.fetchall():
                ContabilidadService.revertir_asiento(cursor,saldo_asiento[0],current_user.id,motivo,request.remote_addr,fecha=voided_at)
        # Devolución en la misma caja: original y contrapartida permanecen visibles.
        execute_sp(
            cursor,
            'ventas.sp_AgruparPagosPorMetodoFactura',
            (invoice_id,),
            fallback_sql='SELECT MetodoPago,SUM(Monto) FROM Pagos WHERE FacturaID=? GROUP BY MetodoPago',
        )
        for method,total in cursor.fetchall():
            if total>0:
                execute_sp(
                    cursor,
                    'ventas.sp_InsertarPagoDevolucionAnulacion',
                    (invoice_id, method, -total, 'Devolución por anulación'),
                    fallback_sql="INSERT INTO Pagos(FacturaID,MetodoPago,Monto,NombreTransferente,MonedaRegistro) VALUES(?,?,?,?,'NIO')",
                )
        execute_sp(
            cursor,
            'ventas.sp_MarcarFacturaAnulada',
            (current_user.id, voided_at, motivo, invoice_id),
            fallback_sql="UPDATE Facturas SET EstadoFiscal='Anulada',AnuladaPor=?,FechaAnulacion=?,MotivoAnulacion=? WHERE ID=?",
        )
        if row[3] and row[3]>1:
            execute_sp(
                cursor,
                'crm.sp_DecrementarComprasCliente',
                (row[3],),
                fallback_sql='UPDATE Clientes SET TotalCompras=CASE WHEN TotalCompras>0 THEN TotalCompras-1 ELSE 0 END WHERE ID=?',
            )
            execute_sp(
                cursor,
                'crm.sp_ActualizarNivelConfianzaCliente',
                (row[3],),
                fallback_sql='UPDATE Clientes SET NivelConfianzaID=CASE WHEN TotalCompras>=10 THEN 3 WHEN TotalCompras>=3 THEN 2 ELSE 1 END WHERE ID=?',
            )
        audit(cursor,current_user.id,'ANULACION_Y_DEVOLUCION','Factura',invoice_id,{'motivo':motivo},request.remote_addr)
        conn.commit()
        flash('Factura anulada y devolución registrada. Conserve el original y todas las copias.','success')
    except (ValueError,ContabilidadError) as error:
        conn.rollback(); flash(str(error),'error')
    except Exception as error:
        conn.rollback()
        current_app.logger.exception('Error al anular factura %s: %s', invoice_id, error)
        flash(f'Error al anular factura: {error}', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin.fiscal'))


@admin_bp.route('/fiscal/exportar')
@login_required
@roles_required('Admin','SuperAdmin')
def export_fiscal():
    today_ni=business_now().date()
    start=date.fromisoformat(request.args.get('desde',today_ni.replace(day=1).isoformat()))
    end=date.fromisoformat(request.args.get('hasta',today_ni.isoformat()))
    if end<start:
        raise ValueError('El fin debe ser igual o posterior al inicio.')
    conn=get_db_connection()
    try:
        cursor=conn.cursor()
        execute_sp(
            cursor,
            'ventas.sp_ExportarFacturasRangoFiscal',
            (start, end),
            fallback_sql='SELECT NumeroFactura,FechaHora,Subtotal,IVA,Total,EstadoFiscal,FechaAnulacion,MotivoAnulacion FROM Facturas WHERE FechaHora>=? AND FechaHora<DATEADD(day,1,CAST(? AS date)) ORDER BY ID',
        )
        stream=io.StringIO(newline=''); writer=csv.writer(stream)
        writer.writerow(['Número','Fecha emisión','Base C$','IVA C$','Total C$','Estado','Fecha anulación','Motivo'])
        for row in cursor.fetchall():
            writer.writerow([("'"+str(v)) if isinstance(v,str) and v[:1] in ('=','+','-','@','\t','\r') else v for v in row])
        return Response('\ufeff'+stream.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=registro-facturas.csv'})
    finally:
        conn.close()
