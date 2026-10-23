"""Adaptador SQL Server y flujo transaccional de preparación DGI."""
import json
import pyodbc
from contextlib import contextmanager
from datetime import date, timedelta

from app.db import get_db_connection, execute_sp
from app.services.dgi_engine import ENGINE_VERSION, analyze, fingerprint, json_dump, monthly_period
from app.services.business_time import invoice_time_evidence, reversal_time_evidence

PROFILE_KEYS = ('fiscal_razon_social', 'fiscal_ruc', 'fiscal_regimen',
                'dgi_obligaciones', 'dgi_responsable', 'dgi_vigente_desde', 'dgi_vigente_hasta')


def audit(cursor, actor, action, entity, entity_id, detail):
    """Reutiliza bitácora fiscal con fecha UTC explícita para los nuevos eventos DGI."""
    execute_sp(
        cursor,
        'fiscal.sp_RegistrarBitacoraFiscalUTC',
        (actor, action, entity, entity_id, json_dump(detail)),
        fallback_sql='''INSERT INTO BitacoraFiscal(Fecha,UsuarioID,Accion,Entidad,EntidadID,Detalle)
        VALUES(SYSUTCDATETIME(),?,?,?,?,?)''',
    )


class DGIMissingSchema(Exception):
    pass


class DGIConflict(Exception):
    pass


class DGINotFound(Exception):
    pass


class DGIStale(DGIConflict):
    """La única escritura previa a esta excepción es invalidar la revisión."""


@contextmanager
def transaction():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; SET LOCK_TIMEOUT 15000;')
        if not execute_sp(
            cursor,
            'fiscal.sp_VerificarEsquemaDGI',
            fallback_sql="SELECT COALESCE(OBJECT_ID('fiscal.DGI_Revisiones','U'), OBJECT_ID('dbo.DGI_Revisiones','U'))",
        ).fetchone()[0]:
            raise DGIMissingSchema()
        yield cursor
        conn.commit()
    except DGIStale:
        conn.commit()  # conservar invalidación y evento, sin otras mutaciones
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            # El pool ODBC puede conservar opciones de sesión. No propagarlas al POS.
            conn.rollback()
            conn.cursor().execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED; SET LOCK_TIMEOUT -1;')
        finally:
            conn.close()


def rows(cursor):
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def search_invoices(*, period_id, text='', state='', sale_type='', start=None, end=None, page=1, size=10):
    """Devuelve solo una página de facturas del período; no carga documentos JSON."""
    from app.services.business_time import business_now
    cursor_connection = get_db_connection()
    try:
        cursor = cursor_connection.cursor()
        try:
            execute_sp(
                cursor,
                'fiscal.sp_ListarFacturasPeriodo',
                (period_id, text or None, state or None,
                 {'Mostrador': 0, 'Encargo': 1}.get(sale_type),
                 start, end, page, size, business_now() - timedelta(hours=24)),
            )
        except pyodbc.Error as error:
            if '(51051)' in str(error):
                raise DGINotFound('Período DGI no encontrado.') from error
            raise
        total_row = cursor.fetchone()
        total = int(total_row[0]) if total_row else 0
        if not cursor.nextset():
            raise RuntimeError('La consulta fiscal no devolvió la página solicitada.')
        invoices = []
        for row in rows(cursor):
            invoices.append({
                'id': row['ID'], 'numero': row['NumeroFactura'],
                'fecha': row['FechaHora'].isoformat(), 'total': f"{row['Total']:.2f}",
                'estado': row['EstadoFiscal'],
                'tipo': 'Encargo' if row['EsEncargo'] else 'Mostrador',
                'cliente': row['Cliente'], 'reciente': bool(row['EsReciente']),
            })
        return {'total': total, 'facturas': invoices}
    finally:
        cursor_connection.close()


def profile(cursor):
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerPerfilDGI',
        fallback_sql="SELECT Clave,Valor FROM ConfiguracionSistema WHERE Clave LIKE 'fiscal[_]%' OR Clave LIKE 'dgi[_]%' ORDER BY Clave",
    )
    config = {r[0]: r[1] for r in cursor.fetchall()}
    return {key: config.get(key, '') for key in PROFILE_KEYS}


def save_profile(cursor, data, actor):
    if data['fiscal_regimen'] != 'Pendiente':
        if not data['fiscal_razon_social'].strip() or not data['fiscal_ruc'].strip():
            raise DGIConflict('Con un régimen activo, razón social y RUC son requisitos del POS. Mantenga Pendiente si aún no dispone de esos datos.')
        for key in ('fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion'):
            row = execute_sp(
                cursor,
                'seguridad.sp_ObtenerConfiguracionClave',
                (key,),
                fallback_sql='SELECT Valor FROM ConfiguracionSistema WHERE Clave=?',
            ).fetchone()
            if not row or not str(row[0]).strip():
                raise DGIConflict('Antes de cambiar el régimen, complete dirección, teléfono y referencia de autorización en Facturación y emisor. Así se conservan los requisitos del POS existente.')
    for key in PROFILE_KEYS:
        execute_sp(
            cursor,
            'seguridad.sp_ActualizarConfiguracionClaveExistente',
            (data[key], key),
            fallback_sql='UPDATE ConfiguracionSistema SET Valor=? WHERE Clave=?',
        )
        if cursor.rowcount != 1:
            raise DGIMissingSchema()
    audit(cursor, actor, 'DGI_PERFIL', 'Sistema', None, {'campos': list(PROFILE_KEYS)})


def periods(cursor):
    execute_sp(
        cursor,
        'fiscal.sp_ListarPeriodosDGI',
        fallback_sql='SELECT TOP 120 ID,Desde,Hasta,Estado FROM DGI_Periodos ORDER BY Desde DESC',
    )
    return rows(cursor)


def get_period(cursor, period_id):
    execute_sp(
        cursor,
        'fiscal.sp_ObtenerPeriodoDGIPorID',
        (period_id,),
        fallback_sql='SELECT ID,Desde,Hasta,Estado FROM DGI_Periodos WITH (UPDLOCK,HOLDLOCK) WHERE ID=?',
    )
    result = rows(cursor)
    if not result:
        raise DGINotFound('Período no encontrado.')
    return result[0]


def create_period(cursor, month, actor):
    start, end = monthly_period(month)
    row = execute_sp(
        cursor,
        'fiscal.sp_ObtenerPeriodoDGIPorRango',
        (start, end),
        fallback_sql='SELECT ID FROM DGI_Periodos WITH (UPDLOCK,HOLDLOCK) WHERE Desde=? AND Hasta=?',
    ).fetchone()
    if row:
        return row[0]
    rid = execute_sp(
        cursor,
        'fiscal.sp_CrearPeriodoDGI',
        (start, end, actor),
        fallback_sql='INSERT INTO DGI_Periodos(Desde,Hasta,CreadoPor) OUTPUT INSERTED.ID VALUES(?,?,?)',
    ).fetchone()[0]
    audit(cursor, actor, 'DGI_PERIODO', 'DGI_Periodo', rid, {'desde': start, 'hasta': end})
    return rid


def snapshot(cursor, period, obligation):
    start, stop = period['Desde'], period['Hasta'] + timedelta(days=1)
    # Ventana ampliada para capturar históricos UTC que caen en el día adyacente.
    candidate_start, candidate_stop = start - timedelta(days=1), stop + timedelta(days=1)
    execute_sp(
        cursor,
        'fiscal.sp_SnapshotDGIVentasCandidatas',
        (candidate_start, candidate_stop, candidate_start, candidate_stop),
        fallback_sql='''SELECT f.ID AS id,f.NumeroFactura AS numero,f.FechaHora AS fecha,
        f.Subtotal AS base,f.IVA AS iva,f.Total AS total,f.EstadoFiscal AS estado,
        f.FechaAnulacion AS anulada_en,f.MotivoAnulacion AS motivo_anulacion,
        f.DocumentoJSON AS documento,a.Fecha AS fecha_asiento,r.Fecha AS fecha_reversion
        FROM Facturas f OUTER APPLY (SELECT TRY_CONVERT(int,JSON_VALUE(
          CASE WHEN ISJSON(f.DocumentoJSON)=1 THEN f.DocumentoJSON ELSE N'{}' END,'$.asiento_id')) AS AsientoID) j
        LEFT JOIN AsientosDiario a ON a.ID=j.AsientoID
        OUTER APPLY (SELECT TOP 1 Fecha FROM AsientosDiario v
          WHERE v.ReferenciaExterna=CONCAT('REV-',j.AsientoID) AND v.TipoDocumento=N'Reversión' ORDER BY v.ID) r
        WHERE (f.FechaHora>=? AND f.FechaHora<?) OR (f.FechaAnulacion>=? AND f.FechaAnulacion<?)
        ORDER BY f.ID''',
    )
    candidates = rows(cursor)
    sales = []
    for row in candidates:
        # No copiar QR, teléfono ni datos del cliente. Conservar huella del original.
        original = row['documento']
        try:
            document = json.loads(original) if original else {}
            row['documento_corrupto'] = bool(original) and not isinstance(document, dict)
        except (ValueError, TypeError):
            document, row['documento_corrupto'] = {}, True
        row.update(invoice_time_evidence(row['fecha'], document, row.pop('fecha_asiento')))
        row['anulada_en_bd'] = row['anulada_en']
        row['anulada_en'] = reversal_time_evidence(row['anulada_en'], row.pop('fecha_reversion'))
        if not (start <= row['fecha'].date() < stop or
                (row['anulada_en'] and start <= row['anulada_en'].date() < stop)):
            continue
        row['documento'] = bool(original)
        row['documento_sha256'] = fingerprint(original) if original else None
        row['detalles'] = []
        sales.append(row)
    by_id = {r['id']: r for r in sales}
    execute_sp(
        cursor,
        'fiscal.sp_SnapshotDGIDetallesVentas',
        (candidate_start, candidate_stop, candidate_start, candidate_stop),
        fallback_sql='''SELECT d.ID AS id,d.FacturaID AS factura_id,d.ProductoID AS producto_id,
        d.Cantidad AS cantidad,d.PrecioUnitario AS precio,d.Subtotal AS subtotal
        FROM DetalleFacturas d JOIN Facturas f ON f.ID=d.FacturaID
        WHERE (f.FechaHora>=? AND f.FechaHora<?) OR (f.FechaAnulacion>=? AND f.FechaAnulacion<?)
        ORDER BY d.ID''',
    )
    for row in rows(cursor):
        source_id = row.pop('factura_id')
        if source_id in by_id:
            by_id[source_id]['detalles'].append(row)
    execute_sp(
        cursor,
        'fiscal.sp_SnapshotDGICompras',
        (start, stop),
        fallback_sql='''SELECT c.ID AS id,c.Fecha AS fecha,c.FacturaProveedor AS numero,
        c.ProveedorID AS proveedor_id,p.Nombre AS proveedor,c.MateriaPrimaID AS materia_id,
        c.Cantidad AS cantidad,c.CostoTotal AS total,c.IVADocumentado AS iva
        FROM ComprasMateriaPrima c LEFT JOIN Proveedores p ON p.ID=c.ProveedorID
        WHERE c.Fecha>=? AND c.Fecha<? ORDER BY c.ID''',
    )
    purchases = rows(cursor)
    execute_sp(
        cursor,
        'fiscal.sp_SnapshotDGIAsientos',
        (start, stop),
        fallback_sql='''SELECT ID AS id,NumeroComprobante AS numero,Fecha AS fecha,
        Estado AS estado,Descripcion AS descripcion,ReferenciaExterna AS referencia
        FROM AsientosDiario WHERE Fecha>=? AND Fecha<? ORDER BY ID''',
    )
    journals = rows(cursor)
    by_id = {r['id']: r for r in journals}
    for row in journals:
        row['detalles'] = []
    execute_sp(
        cursor,
        'fiscal.sp_SnapshotDGIDetallesAsientos',
        (start, stop),
        fallback_sql='''SELECT d.ID AS id,d.AsientoID AS asiento_id,c.Codigo AS cuenta,
        c.Nombre AS nombre,c.Clase AS clase,d.Debe AS debe,d.Haber AS haber
        FROM DetalleAsientos d JOIN AsientosDiario a ON a.ID=d.AsientoID
        JOIN CatalogoCuentas c ON c.ID=d.CuentaID
        WHERE a.Fecha>=? AND a.Fecha<? ORDER BY d.ID''',
    )
    for row in rows(cursor):
        by_id[row.pop('asiento_id')]['detalles'].append(row)
    # Un solo formato persistido y utilizado también para la primera evaluación.
    return json.loads(json_dump(dict(motor=ENGINE_VERSION, alcance='ANALISIS_INTERNO', desde=start, hasta=period['Hasta'],
        obligacion=obligation, perfil=profile(cursor), ventas=sales, compras=purchases, asientos=journals)))


def history(cursor, period_id=None):
    where = 'WHERE r.PeriodoID=?' if period_id else ''
    sp_name = 'fiscal.sp_HistorialRevisionesDGIPorPeriodo' if period_id else 'fiscal.sp_HistorialRevisionesDGITodas'
    execute_sp(
        cursor,
        sp_name,
        (period_id,) if period_id else (),
        fallback_sql=f'''SELECT TOP 100 r.ID,r.PeriodoID,r.Obligacion,r.Version,r.Estado,r.Motor,r.ResultadoJSON,
        r.CreadoEn,r.CreadoPor,r.AprobadoPor,p.Desde,p.Hasta
        FROM DGI_Revisiones r JOIN DGI_Periodos p ON p.ID=r.PeriodoID
        {where} ORDER BY r.ID DESC''',
    )
    return rows(cursor)


def get_review(cursor, review_id):
    execute_sp(
        cursor,
        'fiscal.sp_ObtenerRevisionDGIPorID',
        (review_id,),
        fallback_sql='SELECT * FROM DGI_Revisiones WITH (UPDLOCK,HOLDLOCK) WHERE ID=?',
    )
    result = rows(cursor)
    if not result:
        raise DGINotFound('Revisión no encontrada.')
    return result[0]


def create_review(cursor, period_id, obligation, actor):
    period = get_period(cursor, period_id)
    if period['Estado'] != 'Abierto':
        raise DGIConflict('El período está cerrado. Un administrador debe reabrirlo para generar revisiones.')
    data = snapshot(cursor, period, obligation)
    digest = fingerprint(data)
    execute_sp(
        cursor,
        'fiscal.sp_ObtenerUltimaRevisionDGI',
        (period_id, obligation),
        fallback_sql='''SELECT TOP 1 ID,Version,Huella,Motor,Estado FROM DGI_Revisiones WITH (UPDLOCK,HOLDLOCK)
        WHERE PeriodoID=? AND Obligacion=? ORDER BY Version DESC''',
    )
    previous = cursor.fetchone()
    if previous and previous.Huella == digest and previous.Motor == ENGINE_VERSION and previous.Estado != 'OBSOLETO':
        return previous.ID
    version = previous.Version + 1 if previous else 1
    if previous and previous.Estado != 'OBSOLETO':
        execute_sp(
            cursor,
            'fiscal.sp_MarcarRevisionDGIObsoleta',
            (previous.ID,),
            fallback_sql="UPDATE DGI_Revisiones SET Estado='OBSOLETO' WHERE ID=?",
        )
        audit(cursor, actor, 'DGI_SUSTITUIDA', 'DGI_Revision', previous.ID, {'nueva_version': version})
    rid = execute_sp(
        cursor,
        'fiscal.sp_InsertarRevisionDGI',
        (period_id, obligation, version, ENGINE_VERSION, digest, json_dump(data), json_dump(analyze(data)), actor),
        fallback_sql='''INSERT INTO DGI_Revisiones(PeriodoID,Obligacion,Version,Motor,Huella,
        SnapshotJSON,ResultadoJSON,CreadoPor) OUTPUT INSERTED.ID VALUES(?,?,?,?,?,?,?,?)''',
    ).fetchone()[0]
    audit(cursor, actor, 'DGI_DIAGNOSTICO', 'DGI_Revision', rid, {'version': version, 'huella': digest, 'motor': ENGINE_VERSION})
    return rid


def assert_fresh(cursor, review, actor):
    if review['Estado'] == 'OBSOLETO':
        raise DGIConflict('Esta revisión es obsoleta. Genere una nueva versión del período.')
    data = snapshot(cursor, get_period(cursor, review['PeriodoID']), review['Obligacion'])
    if fingerprint(data) != review['Huella'] or review['Motor'] != ENGINE_VERSION:
        execute_sp(
            cursor,
            'fiscal.sp_MarcarRevisionDGIObsoleta',
            (review['ID'],),
            fallback_sql="UPDATE DGI_Revisiones SET Estado='OBSOLETO' WHERE ID=?",
        )
        audit(cursor, actor, 'DGI_DESACTUALIZADA', 'DGI_Revision', review['ID'], {'huella_anterior': review['Huella']})
        raise DGIStale('Las fuentes o el perfil cambiaron. La aprobación caducó; genere y revise una nueva versión.')


def review_note(cursor, review_id, note, actor):
    review = get_review(cursor, review_id)
    assert_fresh(cursor, review, actor)
    if review['Estado'] not in ('BORRADOR', 'EN_REVISION'):
        raise DGIConflict('La revisión aprobada no se modifica. Genere otra versión si cambian las fuentes.')
    execute_sp(
        cursor,
        'fiscal.sp_RegistrarNotaRevisionDGI',
        (actor, note, review_id),
        fallback_sql="""UPDATE DGI_Revisiones SET Estado='EN_REVISION',RevisadoPor=?,
        RevisadoEn=SYSUTCDATETIME(),NotaRevision=? WHERE ID=?""",
    )
    audit(cursor, actor, 'DGI_REVISION_HUMANA', 'DGI_Revision', review_id, {'estado': 'EN_REVISION'})


def approve(cursor, review_id, actor):
    review = get_review(cursor, review_id)
    assert_fresh(cursor, review, actor)
    if review['Estado'] != 'EN_REVISION' or not review['RevisadoPor'] or not review['NotaRevision']:
        raise DGIConflict('Primero registre la revisión humana y sus observaciones.')
    if json.loads(review['ResultadoJSON'])['bloqueantes']:
        raise DGIConflict('Hay errores bloqueantes. Corrija las fuentes y vuelva a analizar; los comentarios no eliminan errores.')
    execute_sp(
        cursor,
        'fiscal.sp_AprobarRevisionDGI',
        (actor, review_id),
        fallback_sql="""UPDATE DGI_Revisiones SET Estado='APROBADO',AprobadoPor=?,
        AprobadoEn=SYSUTCDATETIME() WHERE ID=?""",
    )
    audit(cursor, actor, 'DGI_APROBACION_INTERNA', 'DGI_Revision', review_id, {'huella': review['Huella']})


def comment(cursor, review_id, finding_id, text, actor):
    review = get_review(cursor, review_id)
    assert_fresh(cursor, review, actor)
    if review['Estado'] not in ('BORRADOR', 'EN_REVISION'):
        raise DGIConflict('Las observaciones de una revisión aprobada están cerradas.')
    if not any(f['id'] == finding_id for f in json.loads(review['ResultadoJSON'])['hallazgos']):
        raise DGINotFound('Hallazgo no encontrado en esta revisión.')
    execute_sp(
        cursor,
        'fiscal.sp_InsertarObservacionDGI',
        (review_id, finding_id, text, actor),
        fallback_sql='INSERT INTO DGI_Observaciones(RevisionID,Hallazgo,Comentario,UsuarioID) VALUES(?,?,?,?)',
    )
    audit(cursor, actor, 'DGI_OBSERVACION', 'DGI_Revision', review_id, {'hallazgo': finding_id})


def set_period_state(cursor, period_id, state, actor):
    period = get_period(cursor, period_id)
    if state == period['Estado']:
        return
    if state == 'Cerrado':
        execute_sp(
            cursor,
            'fiscal.sp_ObtenerUltimasRevisionesPeriodoDGI',
            (period_id,),
            fallback_sql='''SELECT ID FROM DGI_Revisiones r WHERE PeriodoID=? AND Version=
            (SELECT MAX(x.Version) FROM DGI_Revisiones x WHERE x.PeriodoID=r.PeriodoID AND x.Obligacion=r.Obligacion)''',
        )
        ids = [r[0] for r in cursor.fetchall()]
        if not ids:
            raise DGIConflict('No hay una revisión aprobada para cerrar la preparación.')
        for rid in ids:
            review = get_review(cursor, rid)
            assert_fresh(cursor, review, actor)
            if review['Estado'] not in ('APROBADO', 'EXPORTADO'):
                raise DGIConflict('Apruebe todas las últimas revisiones antes de cerrar la preparación.')
    execute_sp(
        cursor,
        'fiscal.sp_ActualizarEstadoPeriodoDGI',
        (state, period_id),
        fallback_sql='UPDATE DGI_Periodos SET Estado=? WHERE ID=?',
    )
    audit(cursor, actor, 'DGI_ESTADO_PERIODO', 'DGI_Periodo', period_id, {'estado': state})
