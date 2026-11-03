"""Preparación tributaria interna integrada al administrador existente."""
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone

from flask import flash, redirect, render_template, request, send_file, url_for, jsonify
from flask_login import current_user

from app.admin import admin_bp
from app.auth.decorators import roles_required
from app.db import execute_sp
from app.services import dgi_repository as repo
from app.services.dgi_engine import ENGINE_VERSION, NOTICE, fingerprint, rule_catalog, money
from app.services.dgi_excel import export_xlsx
from app.services.dgi_repository import audit
from app.services.business_time import business_now, invoice_time_evidence

NICARAGUA = timezone(timedelta(hours=-6))


class DGIInputError(Exception):
    pass


def field(name, maximum, required=True):
    value = request.form.get(name, '').strip()
    if (required and not value) or len(value) > maximum or '\x00' in value:
        raise DGIInputError(f'Complete {name} con un máximo de {maximum} caracteres.')
    return value


def positive_id(value):
    try:
        result = int(value)
        if result <= 0 or result > 2147483647:
            raise ValueError()
        return result
    except (ValueError, TypeError) as error:
        raise DGIInputError('Seleccione un período válido.') from error


@admin_bp.app_template_filter('dgi_money')
def dgi_money(value):
    try:
        return f'C$ {money(value):,.2f}'
    except ValueError:
        return 'Dato inválido'


@admin_bp.app_template_filter('dgi_time')
def dgi_time(value):
    if not value:
        return '—'
    return value.replace(tzinfo=timezone.utc).astimezone(NICARAGUA).strftime('%d/%m/%Y %H:%M')


@admin_bp.app_template_filter('dgi_date')
def dgi_date(value):
    if not value:
        return 'Sin fecha'
    try:
        stamp = datetime.fromisoformat(str(value))
        return stamp.strftime('%d/%m/%Y' if len(str(value)) == 10 else '%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return str(value)


def finding_link(finding):
    if finding.get('tipo'):
        return url_for('admin.dgi_source', kind=finding['tipo'], source_id=finding['origen_id'])
    if finding.get('codigo') in ('PERFIL', 'VIGENCIA'):
        return url_for('admin.dgi_dashboard') + '#perfil'
    if finding.get('codigo') in ('SIN_COMPRAS', 'PROVEEDOR_RUC', 'SOPORTE'):
        return url_for('admin.inventario')
    return '#consolidacion'


@admin_bp.errorhandler(repo.DGIMissingSchema)
def dgi_missing_schema(error):
    return render_template('admin/dgi/message.html', title='Preparación DGI pendiente de instalar',
        message='Falta ejecutar la migración DGI en la base utilizada por esta instalación. Consulte docs/dgi/MANUAL.md. No se aplican migraciones al abrir una pantalla.'), 503


@admin_bp.errorhandler(repo.DGIConflict)
@admin_bp.errorhandler(repo.DGIStale)
def dgi_conflict(error):
    return render_template('admin/dgi/message.html', title='La operación requiere revisión', message=str(error)), 409


@admin_bp.errorhandler(repo.DGINotFound)
def dgi_not_found(error):
    return render_template('admin/dgi/message.html', title='Registro no encontrado', message=str(error)), 404


@admin_bp.errorhandler(DGIInputError)
def dgi_bad_input(error):
    return render_template('admin/dgi/message.html', title='Revise los datos del formulario', message=str(error)), 400


@admin_bp.route('/dgi')
@roles_required('Admin', 'SuperAdmin')
def dgi_dashboard():
    with repo.transaction() as cursor:
        profile = repo.profile(cursor)
        periods = repo.periods(cursor)
        today = business_now().date()
        past = [p for p in periods if p['Desde'] <= today]
        suggested = past[0] if past else (periods[-1] if periods else None)
        selected_id = positive_id(request.args['periodo']) if request.args.get('periodo') else (suggested['ID'] if suggested else None)
        selected = repo.get_period(cursor, selected_id) if selected_id else None
        all_reviews = repo.history(cursor, selected_id) if selected_id else []
        show_history = request.args.get('historial') == '1'
        reviews, seen = [], set()
        any_stale = False
        snapshot_hashes = {}
        for review in all_reviews:
            latest = review['Obligacion'] not in seen
            seen.add(review['Obligacion'])
            if show_history or latest:
                obligation = review['Obligacion']
                if selected and obligation not in snapshot_hashes:
                    snapshot_hashes[obligation] = fingerprint(repo.snapshot(cursor, selected, obligation))
                saved_hash = review.get('Huella')
                if not saved_hash:
                    saved_hash = repo.get_review(cursor, review['ID']).get('Huella')
                hash_matches = bool(selected and saved_hash and snapshot_hashes.get(obligation) == saved_hash)
                is_fresh = review['Estado'] != 'OBSOLETO' and review['Motor'] == ENGINE_VERSION and hash_matches
                review['actual'] = is_fresh
                review['stale'] = not is_fresh
                review['EstadoOriginal'] = review['Estado']
                if not is_fresh and review['Estado'] != 'OBSOLETO':
                    review['Estado'] = 'Requiere Revalidación'
                    if latest:
                        any_stale = True
                summary = json.loads(review.pop('ResultadoJSON'))
                review['errores'] = summary['bloqueantes']
                review['pendientes'] = summary.get('pendientes_configuracion', 0)
                reviews.append(review)
        if selected:
            selected['stale'] = any_stale
            if any_stale and selected['Estado'] == 'Cerrado':
                selected['EstadoOriginal'] = selected['Estado']
                selected['Estado'] = 'Requiere Revalidación'
                for p in periods:
                    if p['ID'] == selected['ID']:
                        p['Estado'] = 'Requiere Revalidación'
                        p['stale'] = True
        execute_sp(
            cursor,
            'fiscal.sp_ListarEventosBitacoraDGI',
            fallback_sql="SELECT TOP 30 Fecha,UsuarioID,Accion,EntidadID FROM BitacoraFiscal WHERE Accion LIKE 'DGI[_]%' ORDER BY ID DESC",
        )
        events = repo.rows(cursor)
    return render_template('admin/dgi/dashboard.html', profile=profile, periods=periods,
        selected=selected, reviews=reviews, events=events, notice=NOTICE,
        month=today.strftime('%Y-%m'), show_history=show_history, engine=ENGINE_VERSION)


@admin_bp.route('/dgi/facturas')
@roles_required('Admin', 'SuperAdmin')
def dgi_invoices():
    """Consulta asincrónica, acotada y autorizada para el período visible."""
    try:
        period_id = positive_id(request.args.get('periodo'))
        page = int(request.args.get('pagina', '1'))
        size = int(request.args.get('tamano', '10'))
        text = request.args.get('buscar', '').strip()
        state = request.args.get('estado', '').strip()
        sale_type = request.args.get('tipo', '').strip()
        start = date.fromisoformat(request.args['desde']) if request.args.get('desde') else None
        end = date.fromisoformat(request.args['hasta']) if request.args.get('hasta') else None
        if page < 1 or page > 100000 or size not in (10, 25, 50) or len(text) > 100:
            raise ValueError()
        if state not in ('', 'Emitida', 'Anulada') or sale_type not in ('', 'Mostrador', 'Encargo'):
            raise ValueError()
        if start and end and start > end:
            raise ValueError()
    except (ValueError, TypeError, DGIInputError):
        return jsonify(error='Revise el período y los filtros de búsqueda.'), 400
    try:
        result = repo.search_invoices(period_id=period_id, text=text, state=state,
                                      sale_type=sale_type, start=start, end=end,
                                      page=page, size=size)
    except repo.DGINotFound as error:
        return jsonify(error=str(error)), 404
    return jsonify(result)


@admin_bp.route('/dgi/perfil', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_profile():
    period_id = positive_id(request.form['periodo_id']) if request.form.get('periodo_id') else None
    data = {key: field(key, 255 if key.startswith('fiscal_') else (2000 if key == 'dgi_obligaciones' else 200),
                       required=False) for key in repo.PROFILE_KEYS}
    if data['fiscal_regimen'] not in ('Pendiente', 'General', 'Cuota fija'):
        raise DGIInputError('Seleccione el régimen registrado o Pendiente.')
    obligations = list(dict.fromkeys(v.strip() for v in data['dgi_obligaciones'].splitlines() if v.strip()))
    if any(len(v) > 200 for v in obligations) or len(obligations) > 10:
        raise DGIInputError('Admite hasta 10 obligaciones, una por línea, hasta 200 caracteres cada una. Puede dejarlas pendientes.')
    data['dgi_obligaciones'] = '\n'.join(obligations)
    try:
        since = date.fromisoformat(data['dgi_vigente_desde']) if data['dgi_vigente_desde'] else None
        until = date.fromisoformat(data['dgi_vigente_hasta']) if data['dgi_vigente_hasta'] else None
        if until and since and until < since:
            raise ValueError()
    except ValueError as error:
        raise DGIInputError('Revise el intervalo de vigencia del perfil.') from error
    with repo.transaction() as cursor:
        if period_id:
            repo.get_period(cursor, period_id)
        repo.save_profile(cursor, data, current_user.id)
    flash('Avance del perfil guardado. Los campos fiscales pendientes no bloquean el diagnóstico interno. Revalide las revisiones que utilizaban el perfil anterior.', 'success')
    return redirect(url_for('admin.dgi_dashboard', periodo=period_id,
                            borrador_guardado='perfil-dgi') + '#perfil')


@admin_bp.route('/dgi/periodos', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_create_period():
    try:
        with repo.transaction() as cursor:
            period_id = repo.create_period(cursor, field('mes', 7), current_user.id)
    except ValueError as error:
        raise DGIInputError(str(error)) from error
    return redirect(url_for('admin.dgi_dashboard', periodo=period_id))


@admin_bp.route('/dgi/periodos/<int:period_id>/estado', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_period_state(period_id):
    state = field('estado', 12)
    if state not in ('Abierto', 'Cerrado'):
        raise DGIInputError('Estado de período inválido.')
    with repo.transaction() as cursor:
        repo.set_period_state(cursor, period_id, state, current_user.id)
    flash('Estado de preparación actualizado. Esta acción no cierra la contabilidad ni presenta una declaración.', 'success')
    return redirect(url_for('admin.dgi_dashboard', periodo=period_id))


@admin_bp.route('/dgi/revisiones', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_create_review():
    period_id, obligation = positive_id(request.form.get('periodo_id')), field('obligacion', 200)
    with repo.transaction() as cursor:
        review_id = repo.create_review(cursor, period_id, obligation, current_user.id)
    return redirect(url_for('admin.dgi_review', review_id=review_id))


@admin_bp.route('/dgi/revisiones/<int:review_id>')
@roles_required('Admin', 'SuperAdmin')
def dgi_review(review_id):
    with repo.transaction() as cursor:
        review = repo.get_review(cursor, review_id)
        data, result = json.loads(review['SnapshotJSON']), json.loads(review['ResultadoJSON'])
        for finding in result['hallazgos']:
            finding['enlace'] = finding_link(finding)
        checks = [f for f in result['hallazgos'] if f.get('categoria', 'DATOS') == 'DATOS']
        configuration = [f for f in result['hallazgos'] if f.get('categoria') == 'CONFIGURACION']
        context = [f for f in result['hallazgos'] if f.get('categoria') == 'CONTEXTO']
        period = repo.get_period(cursor, review['PeriodoID'])
        fresh = review['Estado'] != 'OBSOLETO' and review['Motor'] == ENGINE_VERSION and fingerprint(
            repo.snapshot(cursor, period, review['Obligacion'])) == review['Huella']
        execute_sp(
            cursor,
            'fiscal.sp_ListarObservacionesRevisionDGI',
            (review_id,),
            fallback_sql='SELECT Hallazgo,Comentario,UsuarioID,Fecha FROM DGI_Observaciones WHERE RevisionID=? ORDER BY ID',
        )
        comments = repo.rows(cursor)
        execute_sp(
            cursor,
            'fiscal.sp_ListarExportacionesRevisionDGI',
            (review_id,),
            fallback_sql='SELECT ID,Nombre,SHA256,Fecha,UsuarioID FROM DGI_Exportaciones WHERE RevisionID=? ORDER BY ID DESC',
        )
        exports = repo.rows(cursor)
        execute_sp(
            cursor,
            'fiscal.sp_ListarBitacoraRevisionDGI',
            (review_id,),
            fallback_sql="SELECT Fecha,UsuarioID,Accion FROM BitacoraFiscal WHERE Entidad='DGI_Revision' AND EntidadID=? ORDER BY ID",
        )
        events = repo.rows(cursor)
    return render_template('admin/dgi/review.html', review=review, data=data, result=result,
        period=period, fresh=fresh, comments=comments, exports=exports, events=events,
        rules=rule_catalog(), notice=NOTICE, checks=checks, configuration=configuration, context=context,
        old_engine=review['Motor'] != ENGINE_VERSION)


@admin_bp.route('/dgi/revisiones/<int:review_id>/revisar', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_human_review(review_id):
    note = field('nota', 1000)
    if len(note) < 10:
        raise DGIInputError('Describa la revisión realizada en al menos 10 caracteres.')
    with repo.transaction() as cursor:
        repo.review_note(cursor, review_id, note, current_user.id)
    return redirect(url_for('admin.dgi_review', review_id=review_id))


@admin_bp.route('/dgi/revisiones/<int:review_id>/observaciones', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_comment(review_id):
    finding, comment = field('hallazgo', 24), field('comentario', 1000)
    with repo.transaction() as cursor:
        repo.comment(cursor, review_id, finding, comment, current_user.id)
    return redirect(url_for('admin.dgi_review', review_id=review_id) + '#hallazgos')


@admin_bp.route('/dgi/revisiones/<int:review_id>/aprobar', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_approve(review_id):
    with repo.transaction() as cursor:
        repo.approve(cursor, review_id, current_user.id)
    flash('Revisión aprobada para análisis interno. No constituye aprobación tributaria.', 'success')
    return redirect(url_for('admin.dgi_review', review_id=review_id))


@admin_bp.route('/dgi/revisiones/<int:review_id>/exportar', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_export(review_id):
    with repo.transaction() as cursor:
        review = repo.get_review(cursor, review_id)
        repo.assert_fresh(cursor, review, current_user.id)
        if review['Estado'] not in ('APROBADO', 'EXPORTADO') or json.loads(review['ResultadoJSON'])['bloqueantes']:
            raise repo.DGIConflict('El Excel interno requiere revisión aprobada y sin errores bloqueantes.')
        row = execute_sp(
            cursor,
            'fiscal.sp_ObtenerPrimeraExportacionRevisionDGI',
            (review_id,),
            fallback_sql='SELECT TOP 1 ID FROM DGI_Exportaciones WHERE RevisionID=? ORDER BY ID',
        ).fetchone()
        if row:
            export_id = row[0]
        else:
            content = export_xlsx(review, json.loads(review['SnapshotJSON']), json.loads(review['ResultadoJSON']))
            digest = hashlib.sha256(content).hexdigest()
            name = f'DGI-INTERNO-NO-OFICIAL-r{review_id}-v{review["Version"]}.xlsx'
            export_id = execute_sp(
                cursor,
                'fiscal.sp_InsertarExportacionDGI',
                (review_id, name, digest, content, current_user.id),
                fallback_sql='''INSERT INTO DGI_Exportaciones(RevisionID,Nombre,SHA256,Archivo,UsuarioID)
                OUTPUT INSERTED.ID VALUES(?,?,?,?,?)''',
            ).fetchone()[0]
            execute_sp(
                cursor,
                'fiscal.sp_MarcarRevisionDGIExportada',
                (review_id,),
                fallback_sql="UPDATE DGI_Revisiones SET Estado='EXPORTADO' WHERE ID=?",
            )
            audit(cursor, current_user.id, 'DGI_EXPORTACION_INTERNA', 'DGI_Revision', review_id, {'exportacion': export_id, 'sha256': digest})
    return redirect(url_for('admin.dgi_download', export_id=export_id))


@admin_bp.route('/dgi/exportaciones/<int:export_id>')
@roles_required('Admin', 'SuperAdmin')
def dgi_download(export_id):
    with repo.transaction() as cursor:
        execute_sp(
            cursor,
            'fiscal.sp_ObtenerExportacionDGIPorID',
            (export_id,),
            fallback_sql='SELECT RevisionID,Nombre,Archivo,SHA256 FROM DGI_Exportaciones WHERE ID=?',
        )
        row = cursor.fetchone()
        if not row:
            raise repo.DGINotFound('Exportación no encontrada.')
        review_id, name, content, digest = row
        review = repo.get_review(cursor, review_id)
        repo.assert_fresh(cursor, review, current_user.id)
        if review['Estado'] not in ('APROBADO', 'EXPORTADO') or hashlib.sha256(content).hexdigest() != digest:
            raise repo.DGIConflict('La exportación no tiene una aprobación vigente o su huella no coincide.')
        audit(cursor, current_user.id, 'DGI_DESCARGA_INTERNA', 'DGI_Revision', review_id, {'exportacion': export_id, 'sha256': digest})
    return send_file(io.BytesIO(content), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=name, max_age=0)


@admin_bp.route('/dgi/revisiones/<int:review_id>/diagnostico.xlsx', methods=['POST'])
@roles_required('Admin', 'SuperAdmin')
def dgi_diagnosis_report(review_id):
    with repo.transaction() as cursor:
        review = repo.get_review(cursor, review_id)
        repo.assert_fresh(cursor, review, current_user.id)
        draft = dict(review, Estado='DIAGNÓSTICO SIN APROBACIÓN', AprobadoPor=None, AprobadoEn=None)
        content = export_xlsx(draft, json.loads(review['SnapshotJSON']), json.loads(review['ResultadoJSON']))
        digest = hashlib.sha256(content).hexdigest()
        audit(cursor, current_user.id, 'DGI_REPORTE_DIAGNOSTICO', 'DGI_Revision', review_id,
              {'sha256': digest, 'tipo': 'DIAGNOSTICO_SIN_APROBACION', 'motor': review['Motor']})
    return send_file(io.BytesIO(content), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'DIAGNOSTICO-SIN-APROBACION-r{review_id}.xlsx', max_age=0)


@admin_bp.route('/dgi/revisiones/<int:review_id>/exportar-oficial', methods=['POST'])
@roles_required('SuperAdmin')
def dgi_export_official(review_id):
    raise repo.DGIConflict('PENDIENTE DE VALIDACIÓN: no hay guía, plantilla ni reglas oficiales vigentes verificadas para la obligación y período. Solo está disponible el Excel interno.')


@admin_bp.route('/dgi/fuentes/<kind>/<int:source_id>')
@roles_required('Admin', 'SuperAdmin')
def dgi_source(kind, source_id):
    queries = {
        'factura': ('ventas.sp_ObtenerFuenteFacturaDGI', 'SELECT ID,NumeroFactura,FechaHora,Subtotal,IVA,Total,EstadoFiscal,FechaAnulacion,MotivoAnulacion,DocumentoJSON FROM Facturas WHERE ID=?', 'admin.fiscal'),
        'compra': ('produccion.sp_ObtenerFuenteCompraDGI', '''SELECT c.ID,c.Fecha,c.FacturaProveedor,p.Nombre AS Proveedor,c.MateriaPrimaID,c.Cantidad,c.CostoTotal,c.IVADocumentado
                     FROM ComprasMateriaPrima c LEFT JOIN Proveedores p ON p.ID=c.ProveedorID WHERE c.ID=?''', 'admin.inventario'),
        'asiento': ('contabilidad.sp_ObtenerFuenteAsientoDGI', 'SELECT ID,NumeroComprobante,Fecha,Descripcion,Estado,ReferenciaExterna FROM AsientosDiario WHERE ID=?', 'admin.contabilidad'),
    }
    if kind not in queries:
        raise repo.DGINotFound('Tipo de documento no encontrado.')
    with repo.transaction() as cursor:
        execute_sp(
            cursor,
            queries[kind][0],
            (source_id,),
            fallback_sql=queries[kind][1],
        )
        found = repo.rows(cursor)
        if not found:
            raise repo.DGINotFound('Documento fuente no encontrado.')
        details = []
        if kind == 'factura':
            raw = found[0].pop('DocumentoJSON', None)
            try:
                document = json.loads(raw) if raw else {}
                document = document if isinstance(document, dict) else {}
                entry_id = positive_id(document['asiento_id']) if document.get('asiento_id') else None
            except (ValueError, TypeError, DGIInputError):
                document, entry_id = {}, None
            linked = execute_sp(
                cursor,
                'contabilidad.sp_ObtenerFechaAsientoPorID',
                (entry_id,),
                fallback_sql='SELECT Fecha FROM AsientosDiario WHERE ID=?',
            ).fetchone() if entry_id else None
            evidence = invoice_time_evidence(found[0]['FechaHora'], document, linked[0] if linked else None)
            found[0]['FechaComercial'] = evidence['fecha']
            found[0]['CriterioFecha'] = evidence['criterio_fecha']
            execute_sp(
                cursor,
                'ventas.sp_ObtenerDetallesFuenteFacturaDGI',
                (source_id,),
                fallback_sql='''SELECT d.ID,p.Nombre AS Producto,d.Cantidad,d.PrecioUnitario,d.Subtotal
                FROM DetalleFacturas d LEFT JOIN Productos p ON p.ID=d.ProductoID WHERE d.FacturaID=? ORDER BY d.ID''',
            )
            details = repo.rows(cursor)
        elif kind == 'asiento':
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerDetallesFuenteAsientoDGI',
                (source_id,),
                fallback_sql='''SELECT c.Codigo,c.Nombre,d.Debe,d.Haber FROM DetalleAsientos d
                JOIN CatalogoCuentas c ON c.ID=d.CuentaID WHERE d.AsientoID=? ORDER BY d.ID''',
            )
            details = repo.rows(cursor)
    return render_template('admin/dgi/source.html', source=found[0], kind=kind, source_id=source_id,
                           owner=queries[kind][2], details=details)
