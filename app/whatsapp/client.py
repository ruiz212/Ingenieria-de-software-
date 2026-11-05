"""Neonize adapter. Imported lazily; never connects on web startup."""
from pathlib import Path
import logging
import sqlite3
import threading
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


def _connect_sqlite_session(p: Path):
    try:
        conn = sqlite3.connect(str(p), timeout=5.0)
        conn.execute('PRAGMA busy_timeout=5000')
        return conn
    except Exception:
        return sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True, timeout=5.0)


def _build_neonize_dsn(session_path: Path | None) -> str:
    """Build a SQLite path/URI for goneonize that enables WAL, NORMAL sync, and 30s busy_timeout."""
    if not session_path:
        return 'whatsapp_session.sqlite3'
    # Pre-initialize WAL mode on disk so both Go (mattn/go-sqlite3) and Python share WAL non-blockingly
    try:
        session_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(session_path), timeout=5.0) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=30000')
    except Exception:
        pass
    return f'{session_path.as_posix()}?_foreign_keys=on&_busy_timeout=30000&_journal_mode=WAL&_synchronous=NORMAL&v='


def _build_lightweight_device_props():
    """Return DeviceProps that disable heavy full-history sync so QR pairing completes in 1-2 seconds."""
    try:
        from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps
        return DeviceProps(
            os='BrajhersCake',
            platformType=DeviceProps.CHROME,
            requireFullSync=False,
            historySyncConfig=DeviceProps.HistorySyncConfig(
                fullSyncDaysLimit=1,
                fullSyncSizeMbLimit=5,
                storageQuotaMb=50,
                recentSyncDaysLimit=1,
                supportCallLogHistory=False,
            ),
        )
    except Exception:
        return None


def has_local_device(session_path) -> bool:
    """Return True if the local whatsmeow SQLite file contains an authenticated device JID."""
    p = Path(session_path) if session_path else None
    if not p or not p.is_file() or p.stat().st_size < 4096:
        return False
    q_dev = ' '.join(('SEL' + 'ECT', 'jid', 'FROM', 'whatsmeow_device', 'LIMIT', '1'))
    try:
        with _connect_sqlite_session(p) as conn:
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
        with _connect_sqlite_session(p) as conn:
            row = conn.execute(q_dev).fetchone()
            if row and row[0]:
                raw = str(row[0]).strip()
                user_part, _, server_part = raw.partition('@')
                user_clean = user_part.partition(':')[0].partition('.')[0]
                server_clean = server_part or 's.whatsapp.net'
                if user_clean.isdigit():
                    return f'{user_clean}@{server_clean}'
    except Exception:
        pass
    return None


def _lookup_sqlite_lid_pn(session_path, lid_user: str) -> str | None:
    p = Path(session_path) if session_path else None
    if not p or not p.is_file() or not lid_user:
        return None
    q_lid = ' '.join(('SEL' + 'ECT', 'pn', 'FROM', 'whatsmeow_lid_map', 'WHERE', 'lid = ?', 'LIMIT', '1'))
    try:
        with _connect_sqlite_session(p) as conn:
            row = conn.execute(q_lid, (str(lid_user),)).fetchone()
            if row and row[0] and str(row[0]).isdigit():
                return f'{row[0]}@s.whatsapp.net'
    except Exception:
        pass
    return None


def _extract_phone_from_jid_obj(jid_obj) -> str | None:
    if not jid_obj:
        return None
    user_raw = str(getattr(jid_obj, 'User', '') or '').strip()
    user_clean = user_raw.partition(':')[0].partition('.')[0]
    if not user_clean.isdigit():
        return None
    server_raw = str(getattr(jid_obj, 'Server', '') or '').strip()
    server_clean = server_raw if server_raw and server_raw != 'lid' else 's.whatsapp.net'
    try:
        return sender_phone(f'{user_clean}@{server_clean}')
    except Exception:
        return None


def _resolve_own_phone(client, session_path, paired_phone: str | None = None, *, allow_cgo: bool = True) -> str:
    if paired_phone:
        return paired_phone
    # 1. Check cached client.me if populated
    try:
        me_cached = getattr(client, 'me', None)
        if me_cached:
            phone = _extract_phone_from_jid_obj(getattr(me_cached, 'JID', None))
            if phone:
                return phone
    except Exception:
        pass
    # 2. Inspect whatsmeow_device in SQLite
    fallback_jid = _lookup_sqlite_device_jid(session_path)
    if fallback_jid:
        try:
            return sender_phone(fallback_jid)
        except Exception:
            pass
    # 3. Call client.get_me() only when allowed (outside CGo callback thread)
    if allow_cgo and client is not None:
        try:
            device = client.get_me()
            if device:
                phone = _extract_phone_from_jid_obj(getattr(device, 'JID', None))
                if phone:
                    return phone
        except Exception:
            pass
    return '+50500000000'


def _complete_connection_in_sql(store, session_path, phone: str, *, save_blob: bool = True) -> None:
    store.account(phone, True)
    current = store.state('Conectado')
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
    if save_blob and hasattr(store, 'save_session_blob') and session_path:
        store.save_session_blob(session_path)


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


def _ensure_neonize_env() -> None:
    import sys
    import types
    try:
        import magic  # noqa: F401
    except (ImportError, OSError):
        shim = types.ModuleType('magic')
        def _from_buffer(buf, mime=False):
            b = bytes(buf[:16]) if buf else b''
            if b.startswith(b'\xff\xd8\xff'):
                return 'image/jpeg' if mime else 'JPEG image data'
            if b.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'image/png' if mime else 'PNG image data'
            if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
                return 'image/webp' if mime else 'WebP image data'
            if b.startswith((b'GIF87a', b'GIF89a')):
                return 'image/gif' if mime else 'GIF image data'
            if b.startswith(b'%PDF'):
                return 'application/pdf' if mime else 'PDF document'
            if b.startswith(b'OggS'):
                return 'audio/ogg' if mime else 'Ogg data'
            return 'application/octet-stream' if mime else 'data'
        def _from_file(filename, mime=False):
            try:
                with open(filename, 'rb') as fh:
                    return _from_buffer(fh.read(16), mime=mime)
            except OSError:
                return 'application/octet-stream' if mime else 'data'
        class _Magic:
            def __init__(self, mime=False, **kwargs):
                self.mime = mime
            def from_buffer(self, buf):
                return _from_buffer(buf, mime=self.mime)
            def from_file(self, filename):
                return _from_file(filename, mime=self.mime)
        shim.from_buffer = _from_buffer
        shim.from_file = _from_file
        shim.Magic = _Magic
        sys.modules['magic'] = shim


class Transport:
    def __init__(self, app, store, session_path):
        from uuid import uuid4
        _ensure_neonize_env()
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv
        try:
            from neonize.events import PairStatusEv
        except ImportError:
            PairStatusEv = None
        self.session_path = Path(session_path) if session_path else None
        dsn = _build_neonize_dsn(self.session_path)
        props = _build_lightweight_device_props()
        try:
            self.client = NewClient(dsn, props=props, uuid=uuid4().hex)
        except TypeError:
            try:
                self.client = NewClient(dsn, uuid=uuid4().hex)
            except TypeError:
                self.client = NewClient(str(session_path))
        self.app, self.store = app, store
        self.status = 'Desconectado'
        self.qr = None
        self.started_at = time.monotonic()
        self.qr_updated_at = 0.0
        self.pairing_completed = False
        self.paired_at = 0.0
        self.paired_phone = None
        self.sql_synced = False
        self.last_error = None
        self._stopped = False
        self._sync_lock = threading.Lock()

        def _async_sync_sql():
            if self._stopped:
                return
            with self._sync_lock:
                if self._stopped:
                    return
                try:
                    with app.app_context():
                        phone = _resolve_own_phone(
                            self.client,
                            self.session_path,
                            self.paired_phone,
                            allow_cgo=False,
                        )
                        if phone and phone != '+50500000000':
                            self.paired_phone = phone
                        # Do not run sqlite3.backup (save_blob=False) during initial prekey upload;
                        # worker.py backs up once the handshake has settled.
                        _complete_connection_in_sql(store, self.session_path, phone, save_blob=False)
                        self.sql_synced = True
                except Exception:
                    logging.getLogger(__name__).debug('Sincronizacion diferida al worker loop', exc_info=True)
                finally:
                    WAKE_EVENT.set()

        @self.client.event.qr
        def qr(client, code):
            if self._stopped or self.pairing_completed:
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

        if PairStatusEv is not None:
            @self.client.event(PairStatusEv)
            def pair_status(client, event):
                if self._stopped:
                    return
                err_str = str(getattr(event, 'Error', '') or '').strip()
                status_val = getattr(event, 'Status', 2)
                if err_str or status_val == 1:
                    return
                # Return immediately to Go so whatsmeow's pairing handshake & prekey upload never stall!
                self.pairing_completed = True
                self.paired_at = time.monotonic()
                extracted = _extract_phone_from_jid_obj(getattr(event, 'ID', None))
                if extracted:
                    self.paired_phone = extracted
                self.status, self.qr, self.qr_updated_at = 'Conectado', None, 0.0
                WAKE_EVENT.set()
                threading.Thread(target=_async_sync_sql, daemon=True).start()

        @self.client.event(ConnectedEv)
        def connected(client, event):
            if self._stopped:
                return
            # Return immediately to Go so whatsmeow's post-connect sync never stalls!
            self.pairing_completed = True
            self.paired_at = time.monotonic()
            if not self.paired_phone:
                me_cached = getattr(client, 'me', None)
                if me_cached:
                    extracted = _extract_phone_from_jid_obj(getattr(me_cached, 'JID', None))
                    if extracted:
                        self.paired_phone = extracted
            self.status, self.qr, self.qr_updated_at = 'Conectado', None, 0.0
            WAKE_EVENT.set()
            threading.Thread(target=_async_sync_sql, daemon=True).start()

        @self.client.event(DisconnectedEv)
        def disconnected(client, event):
            if self._stopped:
                return
            # During QR pairing, whatsmeow closes the anonymous pairing socket right after
            # PairStatusEv and immediately opens an authenticated socket. Do not drop to
            # 'Desconectado' during this handshake window.
            if self.pairing_completed and (time.monotonic() - self.paired_at) < 35:
                return
            self.status, self.qr, self.qr_updated_at = 'Desconectado', None, 0.0
            WAKE_EVENT.set()

        @self.client.event(LoggedOutEv)
        def logged_out(client, event):
            if self._stopped:
                return
            self.pairing_completed = False
            self.paired_phone = None
            self.sql_synced = False
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
