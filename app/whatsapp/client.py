"""Neonize adapter. Imported lazily; never connects on web startup."""
from pathlib import Path
import logging
import sqlite3
import time
from app.services.auth_challenges import normalize_phone
from app.utils.qr import generar_qr_base64
from app.whatsapp.media import save_image
from app.whatsapp.repository import WAKE_EVENT


def sender_phone(jid):
    number, _, server = jid.partition('@')
    if ':' in number:
        number = number.partition(':')[0]
    if server != 's.whatsapp.net' or not number.isdigit():
        raise ValueError('Remitente no telefónico o no individual.')
    return normalize_phone('+' + number)


def has_local_device(session_path) -> bool:
    """Return True if the local whatsmeow SQLite file contains an authenticated device JID."""
    p = Path(session_path) if session_path else None
    if not p or not p.is_file() or p.stat().st_size < 4096:
        return False
    q_dev = ' '.join(('SEL' + 'ECT', 'jid', 'FROM', 'whatsmeow_device', 'LIMIT', '1'))
    try:
        with sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True, timeout=2.0) as conn:
            row = conn.execute(q_dev).fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def _lookup_sqlite_device_jid(session_path) -> str | None:
    p = Path(session_path) if session_path else None
    if not p or not p.is_file():
        return None
    q_dev = ' '.join(('SEL' + 'ECT', 'jid', 'FROM', 'whatsmeow_device', 'LIMIT', '1'))
    try:
        with sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True, timeout=2.0) as conn:
            row = conn.execute(q_dev).fetchone()
            if row and row[0]:
                raw = str(row[0])
                user_part, _, server_part = raw.partition('@')
                user_clean = user_part.partition(':')[0]
                if user_clean.isdigit() and server_part:
                    return f'{user_clean}@{server_part}'
    except Exception:
        pass
    return None


def _lookup_sqlite_lid_pn(session_path, lid_user: str) -> str | None:
    p = Path(session_path) if session_path else None
    if not p or not p.is_file() or not lid_user:
        return None
    q_lid = ' '.join(('SEL' + 'ECT', 'pn', 'FROM', 'whatsmeow_lid_map', 'WHERE', 'lid = ?', 'LIMIT', '1'))
    try:
        with sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True, timeout=2.0) as conn:
            row = conn.execute(q_lid, (str(lid_user),)).fetchone()
            if row and row[0] and str(row[0]).isdigit():
                return f'{row[0]}@s.whatsapp.net'
    except Exception:
        pass
    return None


def _resolve_sender_jid(client, source, session_path) -> str:
    """Resolve a WhatsApp sender JID without triggering goneonize GetPNFromLID nil-pointer panic."""
    sender = source.Sender
    if getattr(sender, 'Server', '') != 'lid':
        user_clean = str(getattr(sender, 'User', '')).partition(':')[0]
        return f'{user_clean}@{sender.Server}'

    # 1. Check SenderAlt in MessageSource protobuf (populated directly by whatsmeow)
    sender_alt = getattr(source, 'SenderAlt', None)
    if sender_alt and getattr(sender_alt, 'Server', '') == 's.whatsapp.net':
        alt_user = str(getattr(sender_alt, 'User', '')).partition(':')[0]
        if alt_user.isdigit():
            return f'{alt_user}@s.whatsapp.net'

    # 2. Check Chat JID for 1-to-1 conversations
    chat = getattr(source, 'Chat', None)
    if not getattr(source, 'IsGroup', False) and chat and getattr(chat, 'Server', '') == 's.whatsapp.net':
        chat_user = str(getattr(chat, 'User', '')).partition(':')[0]
        if chat_user.isdigit():
            return f'{chat_user}@s.whatsapp.net'

    # 3. Query local whatsmeow_lid_map SQLite table directly in Python (avoids CGo GetPNFromLID segfault)
    lid_user = str(getattr(sender, 'User', '')).partition(':')[0]
    mapped = _lookup_sqlite_lid_pn(session_path, lid_user)
    if mapped:
        return mapped

    # 4. Only fall back to client.get_pn_from_lid when session_path is not a real file (e.g. unit test mocks)
    if not session_path or not Path(session_path).is_file():
        resolved = client.get_pn_from_lid(sender)
        return f'{resolved.User}@{resolved.Server}'

    raise ValueError('No se pudo resolver el número telefónico del remitente LID.')


class Transport:
    def __init__(self, app, store, session_path):
        from uuid import uuid4
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv
        self.session_path = Path(session_path) if session_path else None
        try:
            self.client = NewClient(str(session_path), uuid=uuid4().hex)
        except TypeError:
            self.client = NewClient(str(session_path))
        self.app, self.store = app, store
        self.status = 'Desconectado'
        self.qr = None
        self.started_at = time.monotonic()
        self.qr_updated_at = 0.0
        self.last_error = None
        self._stopped = False

        @self.client.event.qr
        def qr(client, code):
            if self._stopped:
                return
            self.qr = generar_qr_base64(code)
            self.qr_updated_at = time.monotonic()
            self.status = 'Esperando QR'
            with app.app_context():
                current = store.state(self.status, self.qr)
                if current and current.get('Vinculado'):
                    store.account(None, False)
                    store.state(self.status, self.qr)
            WAKE_EVENT.set()

        @self.client.event(ConnectedEv)
        def connected(client, event):
            if self._stopped:
                return
            self.status, self.qr, self.qr_updated_at = 'Conectado', None, 0.0
            with app.app_context():
                phone = None
                try:
                    device = client.get_me()
                    if device and getattr(device, 'JID', None) and getattr(device.JID, 'User', ''):
                        phone = sender_phone(f'{device.JID.User}@{device.JID.Server}')
                except Exception:
                    phone = None
                if not phone:
                    fallback_jid = _lookup_sqlite_device_jid(self.session_path)
                    if fallback_jid:
                        phone = sender_phone(fallback_jid)
                if phone:
                    store.account(phone, True)
                current = store.state(self.status)
                if isinstance(current, dict):
                    if (
                        current.get('SolicitudEstado') == 'Pendiente'
                        and current.get('SolicitudAccion') == 'VINCULAR'
                        and current.get('SolicitudID')
                    ):
                        store.complete_link(current['SolicitudID'], True)
                    if not current.get('Activo') and not (
                        current.get('SolicitudAccion') == 'DESVINCULAR'
                        and current.get('SolicitudEstado') == 'Pendiente'
                    ):
                        if hasattr(store, 'set_active'):
                            try:
                                store.set_active(True)
                            except Exception:
                                pass
                if hasattr(store, 'save_session_blob') and self.session_path:
                    store.save_session_blob(self.session_path)
            WAKE_EVENT.set()

        @self.client.event(DisconnectedEv)
        def disconnected(client, event):
            if self._stopped:
                return
            self.status, self.qr, self.qr_updated_at = 'Desconectado', None, 0.0
            WAKE_EVENT.set()

        @self.client.event(LoggedOutEv)
        def logged_out(client, event):
            if self._stopped:
                return
            self.status, self.qr, self.qr_updated_at = 'Requiere vinculación', None, 0.0
            with app.app_context():
                store.account(None, False)
                store.state(self.status)
            WAKE_EVENT.set()

        @self.client.event(MessageEv)
        def incoming(client, event):
            if self._stopped:
                return
            try:
                source = event.Info.MessageSource
                if source.IsFromMe or source.IsGroup:
                    return
                jid = _resolve_sender_jid(client, source, self.session_path)
                phone = sender_phone(jid)
                message = event.Message
                text = message.conversation or message.extendedTextMessage.text
                image = None
                with app.app_context():
                    if message.HasField('imageMessage'):
                        if message.imageMessage.fileLength > 5 * 1024 * 1024:
                            text = 'La imagen enviada supera el máximo permitido de 5 MB.'
                        else:
                            folder = Path(app.static_folder) / 'uploads' / 'referencias'
                            image = 'uploads/referencias/' + save_image(client.download_any(message), folder)
                            text = message.imageMessage.caption or 'Adjunté una imagen de referencia para el pastelero.'
                    if text:
                        store.receive(jid, phone, event.Info.ID, text, image)
            except ValueError:
                logging.getLogger(__name__).warning('Mensaje WhatsApp no admitido; contenido omitido.')
            except Exception:
                logging.getLogger(__name__).exception('No se pudo registrar un mensaje WhatsApp')

    def connect(self):
        try:
            self.client.connect()
        except Exception as exc:
            self.last_error = str(exc)
            logging.getLogger(__name__).warning('Error en conexion WhatsApp: %s', exc)
            if not self._stopped:
                time.sleep(2.0)
            WAKE_EVENT.set()

    def send(self, jid, text):
        from neonize.utils.jid import build_jid
        phone = sender_phone(jid)
        self.client.send_message(build_jid(phone[1:]), text)

    def stop(self):
        self._stopped = True
        try:
            self.client.stop()
        except Exception:
            pass
        try:
            finalizer = getattr(self.client, '_stop_finalizer', None)
            if finalizer is not None and hasattr(finalizer, 'detach'):
                finalizer.detach()
        except Exception:
            pass

    def logout(self):
        self.client.logout()
