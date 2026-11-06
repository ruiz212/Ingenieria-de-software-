"""Short SQL transactions. All calls use a fresh connection and close its identity."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from uuid import uuid4
from app.db import get_db_connection, as_db_role

WAKE_EVENT = threading.Event()
_CATALOG_CACHE = {'expires': 0.0, 'items': None}
_VERIFY_LOCK = threading.Lock()
_VERIFY_FAILURES: dict = {}
_VERIFY_MAX_FAILURES = 5
_VERIFY_WINDOW = 900.0
OTP_PREFIX = '🔐 Brajher\'s Cake: tu código de verificación'

_CONFIRM_VARIANTS = frozenset({
    'CONFIRMAR',
    'CONFIRMO',
    'SI CONFIRMAR',
    'SÍ CONFIRMAR',
    'SI, CONFIRMAR',
    'SÍ, CONFIRMAR',
    'OK CONFIRMAR',
    'SI CONFIRMO',
    'SÍ CONFIRMO',
})


def rows(cursor):
    keys = [c[0] for c in cursor.description] if cursor.description else []
    return [dict(zip(keys, row)) for row in cursor.fetchall()] if keys else []


@contextmanager
def connection(worker=False):
    conn = get_db_connection(inject_context=not worker, apply_role=not worker)
    try:
        cur = conn.cursor()
        if worker:
            cur.execute("EXECUTE AS USER='usr_bd_whatsapp'")
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if worker:
            try:
                conn.cursor().execute('REVERT')
                conn.commit()
            except Exception:
                pass
        conn.close()


def _clean_command_text(raw):
    if not isinstance(raw, str):
        return ''
    cleaned = re.sub(r'[.!¡¿,\s]+$', '', raw.strip())
    cleaned = re.sub(r'^[¡¿\s]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).upper()


class Store:
    def request_link(self, action, revision):
        try:
            with connection() as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppSolicitarVinculo ?,?,?', action, revision, uuid4().hex)
                result = rows(cur)[0]
        except Exception as exc:
            if '52027' not in str(exc):
                raise
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppLeerControl')
                ctrl = rows(cur)[0]
                if ctrl.get('SolicitudEstado') == 'Pendiente' and ctrl.get('SolicitudAccion') == 'DESVINCULAR':
                    cur.execute('EXEC crm.sp_WhatsAppCompletarVinculo ?,?,?', ctrl.get('SolicitudID'), True, None)
                    cur.execute('EXEC crm.sp_WhatsAppLeerControl')
                    ctrl = rows(cur)[0]
            with connection() as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppSolicitarVinculo ?,?,?', action, ctrl.get('ConnectionRevision', revision), uuid4().hex)
                result = rows(cur)[0]
        WAKE_EVENT.set()
        return result

    def complete_link(self, operation, success, error=None):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppCompletarVinculo ?,?,?', operation, success, error)

    def account(self, phone, linked):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppCuenta ?,?', phone, linked)

    def set_active(self, enabled):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppActivar ?', bool(enabled))

    def save_session_blob(self, session_path):
        import base64
        import sqlite3
        import tempfile
        import zlib
        from pathlib import Path
        from app.whatsapp.client import has_local_device
        p = Path(session_path) if session_path else None
        if not p or not has_local_device(p):
            return False
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as tmp:
                tmp_path = Path(tmp.name)
            with sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True, timeout=3.0) as src:
                with sqlite3.connect(str(tmp_path)) as dst:
                    src.backup(dst)
            raw = tmp_path.read_bytes()
            encoded = base64.b64encode(zlib.compress(raw, level=6)).decode('ascii')
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppGuardarSesion ?', encoded)
            return True
        except Exception:
            logging.getLogger(__name__).debug('No se pudo respaldar sesion WhatsApp en SQL', exc_info=True)
            return False
        finally:
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def restore_session_blob(self, session_path):
        import base64
        import zlib
        from pathlib import Path
        from app.whatsapp.client import has_local_device
        p = Path(session_path) if session_path else None
        if not p:
            return False
        if has_local_device(p):
            return True
        try:
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppLeerSesion')
                row = cur.fetchone()
                if not row or not row[0]:
                    return False
                raw = zlib.decompress(base64.b64decode(row[0].encode('ascii')))
            p.parent.mkdir(parents=True, exist_ok=True)
            for suffix in ('-wal', '-shm', '-journal'):
                aux = Path(str(p) + suffix)
                try:
                    if aux.exists():
                        aux.unlink()
                except OSError:
                    pass
            p.write_bytes(raw)
            return has_local_device(p)
        except Exception:
            logging.getLogger(__name__).debug('No se pudo restaurar sesion WhatsApp desde SQL', exc_info=True)
            return False

    def state(self, status=None, qr=None):
        with connection(True) as (_, cur):
            if status:
                cur.execute('EXEC crm.sp_WhatsAppHeartbeat ?,?,?,?', status, qr, qr, qr)
            cur.execute('EXEC crm.sp_WhatsAppLeerControl')
            return rows(cur)[0]

    def receive(self, jid, phone, message_id, text, image=None):
        from app.whatsapp.security import sanitize_incoming_text
        clean_text = sanitize_incoming_text(text) or text[:4000]
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppBuscarSesion ?', jid)
            row = cur.fetchone()
            if not row:
                cur.execute('EXEC crm.sp_WhatsAppCrearSesion ?,?,?', jid, phone, uuid4().hex)
                sid = cur.fetchone()[0]
                cur.execute('EXEC crm.sp_WhatsAppConsentimiento ?,?', True, sid)
            else:
                sid = row[0]
            cur.execute('EXEC crm.sp_WhatsAppBuscarMensaje ?,?', sid, message_id)
            if cur.fetchone():
                return False
            cur.execute('EXEC crm.sp_WhatsAppContarRecientes ?', sid)
            if cur.fetchone()[0] >= 6:
                return False
            cur.execute('EXEC crm.sp_WhatsAppInsertarMensaje ?,?,?,?', sid, message_id, clean_text[:4000], image)
            cur.execute('EXEC crm.sp_WhatsAppActualizarImagen ?,?', None, sid)
        WAKE_EVENT.set()
        return True

    def next_message(self):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppMarcarFallidos')
            cur.execute('EXEC crm.sp_WhatsAppSiguienteMensaje')
            result = rows(cur)
            if not result:
                return None
            item = result[0]
            cur.execute('EXEC crm.sp_WhatsAppIntentarMensaje ?', item['ID'])
            cur.execute('EXEC crm.sp_WhatsAppPrepararMensaje ?,?,?', item['id'], item['Imagen'], item['Texto'])
            return item

    def history(self, sid):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppHistorial ?,?', sid, sid)
            return [
                {'role': r['Tipo'], 'text': r['Texto']}
                for r in reversed(rows(cur))
                if r.get('Texto') not in (
                    'No pude completar la consulta. Escribe HUMANO para que te atienda una persona.',
                    'El asistente no está disponible. Escribe HUMANO para que te atienda el equipo.',
                ) and not str(r.get('Texto') or '').startswith(OTP_PREFIX)
            ]

    def finish(self, item, text):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppRevision ?', item['id'])
            session = cur.fetchone()
            cur.execute('EXEC crm.sp_WhatsAppCompletarMensaje ?', item['ID'])
            if text and session[0] == item['Revision'] and session[1] == 'IA':
                self.enqueue(cur, item['id'], f"reply:{item['ID']}", text, 'IA', session[0])
        if text:
            WAKE_EVENT.set()

    @staticmethod
    def enqueue(cur, sid, key, text, kind, revision):
        cur.execute('EXEC crm.sp_WhatsAppEncolar ?,?,?,?,?,?', key, sid, key, text[:4000], kind, revision)
        WAKE_EVENT.set()

    def command(self, item):
        raw = item.get('Texto', '')
        text = raw.strip().upper()
        normalized = _clean_command_text(raw)
        has_pending = bool(item.get('Pendiente'))
        is_confirm = text == 'CONFIRMAR' or (has_pending and normalized in _CONFIRM_VARIANTS)
        is_cancel = has_pending and normalized in ('CANCELAR', 'ANULAR')
        if not is_confirm and not is_cancel and normalized not in (
            'HUMANO', 'IA', 'ASISTENTE', 'BOT', 'REACTIVAR IA', 'AVISOS SI', 'AVISOS SÍ', 'AVISOS NO'
        ):
            return False, None
        if is_cancel:
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppLimpiarBorrador ?', item['id'])
            return True, 'Operación pendiente cancelada. Indícame si deseas realizar otra consulta o cotización.'
        if is_confirm:
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppLeerAccion ?', f"confirm:{item['ID']}")
                prior = cur.fetchone()
                if prior:
                    return True, str(json.loads(prior[0]))
            if not item.get('Pendiente'):
                return True, 'No hay una operación pendiente de confirmar.'
            pending = json.loads(item['Pendiente'])
            if datetime.fromisoformat(pending['expires']) < datetime.now(timezone.utc):
                with connection(True) as (_, cur):
                    cur.execute('EXEC crm.sp_WhatsAppLimpiarBorrador ?', item['id'])
                return True, 'La confirmación venció. Solicita nuevamente la operación para revisar sus detalles.'
            result = self.tool(item, pending['name'], pending['args'], f"confirm:{item['ID']}", confirm=True)
            if 'cotizacion' in result:
                return True, f"Solicitud {result['cotizacion']} registrada. El pastelero revisará el precio y te notificaremos por esta vía."
            return True, f"Cotización COT-{result['cotizacion_id']:04d}: decisión registrada ({result['decision']}). El adelanto y la factura se gestionan en caja."
        with connection(True) as (_, cur):
            if normalized == 'HUMANO':
                cur.execute('EXEC crm.sp_WhatsAppHandoff ?', item['id'])
                # The acknowledgment is human-mode compatible.
                self.enqueue(cur, item['id'], f"handoff:{item['ID']}", 'Tu conversación está en atención humana.', 'Humano', item['Revision'] + 1)
                return True, None
            if normalized in ('IA', 'ASISTENTE', 'BOT', 'REACTIVAR IA'):
                cur.execute('EXEC crm.sp_WhatsAppModo ?,?', 'IA', item['id'])
                self.enqueue(cur, item['id'], f"reactivate:{item['ID']}", "Asistente virtual de Brajher's Cake reactivado. ¿En qué te puedo ayudar hoy?", 'IA', item['Revision'] + 1)
                return True, None
            enabled = normalized != 'AVISOS NO'
            cur.execute('EXEC crm.sp_WhatsAppConsentimiento ?,?', enabled, item['id'])
            return True, ('Avisos de cotizaciones y pedidos activados para tu número.'
                          if enabled else 'Avisos automáticos desactivados. Escribe AVISOS SI cuando desees reactivarlos.')

    def tool(self, session, name, args, key, confirm=False):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppLeerAccion ?', key)
            previous = cur.fetchone()
            if previous:
                return json.loads(previous[0])
            cur.execute('EXEC crm.sp_WhatsAppValidarSesion ?', session['id'])
            current = cur.fetchone()
            if not current or current[0] != 'IA' or current[1] != session['Revision']:
                raise PermissionError('Conversación pausada o modificada.')
            cur.execute('EXEC crm.sp_WhatsAppActivo')
            if not cur.fetchone()[0]:
                raise PermissionError('Bot apagado.')
            if name in ('agendar_cotizacion_pastel', 'responder_cotizacion') and not confirm:
                if name == 'responder_cotizacion':
                    cur.execute('EXEC crm.sp_WhatsAppPrecio ?,?', session['id'], args['cotizacion_id'])
                    quote = cur.fetchone()
                    if not quote or quote[0] is None:
                        raise ValueError('Cotización ajena o no disponible para responder.')
                    args = dict(args, precio_esperado=str(quote[0]))
                pending = json.dumps({'name': name, 'args': args,
                                      'expires': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}, ensure_ascii=False)
                cur.execute('EXEC crm.sp_WhatsAppBorrador ?,?', pending, session['id'])
                details = (f"Nombre: {args['nombre']}. Pedido: {args['especificaciones']}. Entrega: {args['fecha_entrega']}. Precio pendiente de valoración."
                           if name == 'agendar_cotizacion_pastel' else
                           f"Cotización COT-{args['cotizacion_id']:04d}. Precio: C$ {args['precio_esperado']}. Decisión: {args['decision']}.")
                result = {'requiere_confirmacion': True, 'detalles': args,
                          'mensaje': details + ' Escribe CONFIRMAR para registrar esta operación. Vence en 15 minutos.'}
            elif name == 'agendar_cotizacion_pastel':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?,?,?,?,?', session['id'], 'crear', None, args['nombre'], args['especificaciones'], args['fecha_entrega'])
                result = {'cotizacion': f'COT-{cur.fetchone()[0]:04d}', 'estado': 'Pendiente'}
            elif name == 'responder_cotizacion':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?,?,?,?,?,?', session['id'], args['decision'], args['cotizacion_id'], None, None, None, args['precio_esperado'])
                result = {'cotizacion_id': cur.fetchone()[0], 'decision': args['decision']}
            elif name == 'consultar_mis_cotizaciones':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?', session['id'], 'listar')
                result = rows(cur)
                for row in result:
                    if 'ID' in row and 'Codigo' not in row:
                        row['Codigo'] = f"COT-{int(row['ID']):04d}"
                    # Never hand internal file paths to the model; only whether a photo exists.
                    row['TieneFotoReferencia'] = bool(row.pop('RutaImagenReferencia', None))
            elif name == 'adjuntar_foto_cotizacion':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?,?', session['id'], 'imagen', args['cotizacion_id'])
                row = cur.fetchone()
                result = {'cotizacion': f"COT-{int(row[0]):04d}", 'foto_adjuntada': True}
            elif name in ('consultar_mis_pedidos', 'rastrear_pedido'):
                code = args.get('codigo_o_factura') or args.get('codigo_seguimiento')
                result = self._verified_order(cur, session, code, args.get('nombre_cliente'))
            elif name in ('consultar_catalogo', 'obtener_recomendaciones_cliente'):
                now = time.monotonic()
                if name == 'consultar_catalogo' and _CATALOG_CACHE['items'] is not None and _CATALOG_CACHE['expires'] > now:
                    result = _CATALOG_CACHE['items']
                else:
                    with as_db_role(cur, 'db_rol_portal_cliente'):
                        cur.execute('EXEC catalogo.sp_ObtenerProductosPOS')
                        raw_items = [r for r in rows(cur) if not r.get('EsFicticio')][:100]
                        result = [
                            {
                                'ID': r.get('ID'),
                                'Nombre': r.get('Nombre'),
                                'Categoria': r.get('Categoria'),
                                'PrecioBase': r.get('PrecioBase'),
                                'PorcentajeDescuento': r.get('PorcentajeDescuento', 0),
                            }
                            for r in raw_items
                        ]
                    if name == 'consultar_catalogo':
                        _CATALOG_CACHE['items'] = result
                        _CATALOG_CACHE['expires'] = now + 60.0
                if name == 'obtener_recomendaciones_cliente':
                    from types import SimpleNamespace
                    from app.services.marketing_repository import store_recommendations, load_marketing_catalog
                    with as_db_role(cur, 'db_rol_portal_cliente'):
                        catalog = load_marketing_catalog(cur)
                        recommended = store_recommendations(cur, catalog, SimpleNamespace(is_authenticated=False))
                    result = {'tipo': 'tendencias generales, sin historial personal', 'productos': recommended}
            elif name == 'transferir_a_humano':
                cur.execute('EXEC crm.sp_WhatsAppHandoff ?', session['id'])
                result = {'atencion': 'HUMANO'}
                self.enqueue(cur, session['id'], key + ':handoff', 'Tu conversación está en atención humana.', 'Humano', current[1] + 1)
            else:
                raise ValueError('Herramienta no autorizada.')
            if confirm:
                cur.execute('EXEC crm.sp_WhatsAppLimpiarBorrador ?', session['id'])
            # JSON converts SQL Decimal/datetime without losing their display value.
            payload = json.dumps(result, ensure_ascii=False, default=str)
            cur.execute('EXEC crm.sp_WhatsAppGuardarAccion ?,?,?,?', key, session['id'], name, payload)
            return json.loads(payload)

    @staticmethod
    def _verification_blocked(session_id):
        now = time.monotonic()
        with _VERIFY_LOCK:
            attempts = [t for t in _VERIFY_FAILURES.get(session_id, []) if now - t < _VERIFY_WINDOW]
            _VERIFY_FAILURES[session_id] = attempts
            return len(attempts) >= _VERIFY_MAX_FAILURES

    @staticmethod
    def _record_verification_failure(session_id):
        with _VERIFY_LOCK:
            _VERIFY_FAILURES.setdefault(session_id, []).append(time.monotonic())

    def _verified_order(self, cur, session, code, holder_name):
        """Share an order only when BOTH the holder's name and its private code/invoice match."""
        from app.whatsapp.security import verify_holder_name
        denied = {
            'verificado': False,
            'mensaje': ('No pudimos validar el pedido con esos datos. Por privacidad solo compartimos el estado '
                        'cuando el nombre del titular y el código de seguimiento (o número de factura) coinciden.'),
        }
        sid = session['id']
        if self._verification_blocked(sid):
            return {'verificado': False, 'bloqueado': True,
                    'mensaje': ('Por seguridad se pausaron las consultas de pedidos de este chat durante 15 minutos '
                                'por varios intentos no válidos. Puedes escribir HUMANO para que te atienda el equipo.')}
        raw = re.sub(r'\s+', '', str(code or '')).upper()
        if not raw or len(raw) > 30 or not re.fullmatch(r'[A-Z0-9-]+', raw):
            self._record_verification_failure(sid)
            return denied
        invoice_digits = None
        match = re.fullmatch(r'(?:FAC-?)?0*(\d{1,10})', raw)
        if match and (raw.startswith('FAC') or len(raw) < 10):
            invoice_digits = match.group(1)
        record = None
        # 1) Orders whose contact phone matches this WhatsApp number (code OR invoice accepted).
        for row in self._orders_for_phone(cur, sid):
            numero = str(row.get('NumeroFactura') or '').upper()
            digits = re.sub(r'\D', '', numero).lstrip('0')
            if raw == str(row.get('CodigoSeguimiento') or '').upper() or raw == numero or (
                    invoice_digits and digits == invoice_digits):
                record = row
                break
        # 2) Private tracking code from another phone (e.g. a gift): still needs the holder's name.
        if record is None and invoice_digits is None and len(raw) >= 8:
            with as_db_role(cur, 'db_rol_portal_cliente'):
                cur.execute('EXEC ventas.sp_SeguimientoEncargoPublico ?', raw[:20])
                found = rows(cur)
                if found:
                    cur.execute('EXEC ventas.sp_SeguimientoAdelantoPublico ?', raw[:20])
                    paid_row = cur.fetchone()
                    record = dict(found[0], CodigoSeguimiento=raw,
                                  Pagado=paid_row[0] if paid_row and paid_row[0] is not None else 0)
        if record is None or not verify_holder_name(holder_name, record.get('NombreCliente') or ''):
            self._record_verification_failure(sid)
            return denied
        total = float(record.get('Total') or 0)
        paid = float(record.get('Pagado') or 0)
        return {
            'verificado': True,
            'NumeroFactura': record.get('NumeroFactura'),
            'Estado': record.get('Estado'),
            'FechaEntrega': record.get('FechaEntrega'),
            'Total': total,
            'SaldoPendiente': max(0.0, round(total - paid, 2)),
            'PastelPersonalizado': bool(record.get('Especificaciones')),
        }

    @staticmethod
    def _orders_for_phone(cur, sid):
        try:
            cur.execute('EXEC crm.sp_WhatsAppPedidosCliente ?', sid)
            return [r for r in rows(cur) if r.get('NumeroFactura')]
        except Exception:
            logging.getLogger(__name__).debug('sp_WhatsAppPedidosCliente no disponible en este cursor')
            return []

    def outgoing(self):
        with connection(True) as (_, cur):
            # Singleton worker owns delivery; revision invalidates stale generated responses.
            cur.execute('EXEC crm.sp_WhatsAppCancelarObsoletos')
            cur.execute('EXEC crm.sp_WhatsAppSiguienteEnvio')
            result = rows(cur)
            return result[0] if result else None

    def deliver(self, outgoing, send):
        # Lock only channel state during dispatch. A successful human takeover cannot
        # race with an old AI send; no POS/invoice locks are acquired here.
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppBloquearEnvio ?', outgoing['SesionID'])
            session = cur.fetchone()
            cur.execute('EXEC crm.sp_WhatsAppBloquearControl')
            active = cur.fetchone()[0]
            if not active:
                return
            if ((outgoing['Tipo'] == 'IA' and (session[0] != 'IA' or session[1] != outgoing['Revision']))
                    or (outgoing['Tipo'] == 'Aviso' and not session[2])):
                cur.execute('EXEC crm.sp_WhatsAppCancelarEnvio ?', outgoing['ID'])
                return
            success = False
            try:
                send(outgoing['JID'], outgoing['Texto'])
                success = True
            except Exception:
                logging.getLogger(__name__).warning('Envío WhatsApp falló ID=%s', outgoing['ID'])
            cur.execute('EXEC crm.sp_WhatsAppResultadoEnvio ?,?', success, outgoing['ID'])


def enqueue_phone_notification(phone, key, text):
    """Ensure a WhatsApp session exists for the given phone and queue a notification if active."""
    from app.whatsapp.security import normalize_nicaragua_phone
    norm_phone, jid, _ = normalize_nicaragua_phone(phone)
    if not norm_phone or not jid or not key or not text:
        return False
    try:
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppActivo')
            active_row = cur.fetchone()
            if not active_row or not active_row[0]:
                return False
            cur.execute('EXEC crm.sp_WhatsAppBuscarSesion ?', jid)
            row = cur.fetchone()
            if not row:
                cur.execute('EXEC crm.sp_WhatsAppCrearSesion ?,?,?', jid, norm_phone, uuid4().hex)
                sid = cur.fetchone()[0]
                cur.execute('EXEC crm.sp_WhatsAppConsentimiento ?,?', True, sid)
            else:
                sid = row[0]
            cur.execute('EXEC crm.sp_WhatsAppBloquearEnvio ?', sid)
            sess = cur.fetchone()
            if not sess or not sess[2]:
                return False
            Store.enqueue(cur, sid, key, text, 'Aviso', sess[1])
            return True
    except Exception:
        logging.getLogger(__name__).debug('No se pudo encolar notificación directa para %s', norm_phone, exc_info=True)
        return False


def _format_quote_notification(quote_id, estado, precio=None, fecha_entrega=None):
    code = f'COT-{int(quote_id):04d}'
    fecha_txt = f' (Entrega: {fecha_entrega})' if fecha_entrega else ''
    if estado == 'Cotizada' and precio is not None:
        return (
            f"🍰 Brajher's Cake: Tu cotización {code} está lista por C$ {precio}{fecha_txt}. "
            f"Indica el código {code} y si deseas aceptarla o rechazarla."
        )
    if estado == 'Rechazada':
        return (
            f"🍰 Brajher's Cake: Tu cotización {code} fue marcada como Rechazada. "
            f"Escribe HUMANO si deseas ajustar tu pedido."
        )
    if estado == 'Aceptada':
        precio_txt = f' por C$ {precio}' if precio is not None else ''
        return (
            f"🍰 Brajher's Cake: Confirmamos tu aceptación de la cotización {code}{precio_txt}. "
            f"Recuerda realizar el adelanto mínimo del 50% en caja."
        )
    return None


def _format_order_notification(numero_factura, estado, codigo_seguimiento=None, fecha_entrega=None, saldo=None):
    code_txt = f' Código de seguimiento: {codigo_seguimiento}.' if codigo_seguimiento else ''
    fecha_txt = f' (Entrega: {fecha_entrega})' if fecha_entrega else ''
    saldo_txt = f' Saldo pendiente: C$ {saldo:.2f}.' if isinstance(saldo, (int, float)) else ''
    if estado == 'Pendiente':
        return f"🧾 Brajher's Cake: Tu pedido {numero_factura} fue registrado (Estado: Pendiente){fecha_txt}.{saldo_txt}{code_txt}"
    if estado == 'En Proceso':
        return f"👩‍🍳 Brajher's Cake: Tu pedido {numero_factura} está En Proceso en pastelería{fecha_txt}.{saldo_txt}{code_txt}"
    if estado == 'Listo':
        return f"🎂 Brajher's Cake: ¡Tu pedido {numero_factura} está Listo para retirar!{saldo_txt} Consulta el saldo con tu código privado de seguimiento{(' ' + codigo_seguimiento) if codigo_seguimiento else ''}."
    if estado == 'Entregado':
        return f"✅ Brajher's Cake: Tu pedido {numero_factura} fue marcado como Entregado. ¡Gracias por preferirnos!"
    return None


def notify(cursor, kind, entity_id, *, phone=None, estado=None, precio=None,
           numero_factura=None, codigo_seguimiento=None, fecha_entrega=None, saldo=None):
    """Trigger SQL stored procedure and ensure phone-associated session delivery."""
    if os.environ.get('WHATSAPP_ENABLED', '0') != '1':
        return
    # 1. Execute SQL stored procedure (standard contract with ownership chaining)
    try:
        cursor.execute('EXEC crm.sp_WhatsAppNotificar ?,?', kind, entity_id)
    except Exception:
        logging.getLogger(__name__).debug('sp_WhatsAppNotificar omitido en cursor actual', exc_info=True)
    # 2. If phone is not provided, query notification metadata via stored procedure
    if not phone and kind in ('pedido', 'cotizacion'):
        try:
            cursor.execute('EXEC crm.sp_WhatsAppDatosAviso ?,?', kind, entity_id)
            row = cursor.fetchone()
            if row:
                if kind == 'pedido':
                    phone = row[0]
                    numero_factura = numero_factura or row[1]
                    codigo_seguimiento = codigo_seguimiento or row[2]
                    estado = estado or row[3]
                    fecha_entrega = fecha_entrega or row[4]
                    total = row[5] or 0
                    pagado = row[6] or 0
                    if saldo is None and total is not None and pagado is not None:
                        saldo = max(0.0, float(total) - float(pagado))
                elif kind == 'cotizacion':
                    phone = row[0]
                    estado = estado or row[1]
                    precio = precio if precio is not None else row[2]
                    fecha_entrega = fecha_entrega or row[3]
        except Exception:
            logging.getLogger(__name__).debug('No se pudieron resolver datos de aviso para %s:%s', kind, entity_id, exc_info=True)
    # 3. Also ensure phone-based session creation and idempotent queueing when phone is provided
    if phone and estado:
        if kind == 'cotizacion':
            text = _format_quote_notification(entity_id, estado, precio=precio, fecha_entrega=fecha_entrega)
            key = f"quote:{entity_id}:{estado}:{precio if precio is not None else 0}"
        elif kind == 'pedido' and numero_factura:
            text = _format_order_notification(
                numero_factura, estado,
                codigo_seguimiento=codigo_seguimiento,
                fecha_entrega=fecha_entrega,
                saldo=saldo,
            )
            key = f"order:{entity_id}:{estado}"
        else:
            text = key = None
        if text and key:
            enqueue_phone_notification(phone, key, text)
    WAKE_EVENT.set()


def send_whatsapp_verification_code(phone, code):
    """Enqueue a 6-digit verification code directly to user's WhatsApp."""
    if not phone or not code:
        return False
    text = f"{OTP_PREFIX} es: {code}. Válido por 10 minutos. Por seguridad, no compartas este código con nadie."
    key = f"otp:{phone}:{code}"
    return enqueue_phone_notification(phone, key, text)
