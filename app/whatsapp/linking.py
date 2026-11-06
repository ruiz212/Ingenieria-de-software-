"""Account lifecycle, QR authorization, and automatic worker supervision."""
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from flask import current_app, has_request_context, request, session

_WORKER_LOCK = threading.Lock()
_WORKER_PROC = None
_SUPERVISOR_STARTED = False


def public_state(state):
    result = {key: state.get(key) for key in (
        'Estado', 'Activo', 'QR', 'QRExpira', 'Vinculado', 'CuentaTelefono',
        'ConnectionRevision', 'SolicitudAccion', 'SolicitudEstado', 'SolicitudError')}
    grant = session.get('wa_pairing', {})
    session_allowed = (
        grant.get('until', 0) > time.time()
        and (
            grant.get('revision') == state.get('ConnectionRevision')
            or (
                grant.get('solicitud_id')
                and grant.get('solicitud_id') == state.get('SolicitudID')
                and state.get('SolicitudAccion') == 'VINCULAR'
                and state.get('SolicitudEstado') == 'Pendiente'
            )
        )
    )
    sql_link_allowed = (
        state.get('SolicitadoPor') is not None
        and state.get('SolicitudAccion') == 'VINCULAR'
        and state.get('SolicitudEstado') == 'Pendiente'
        and not state.get('Vinculado')
    )
    allowed = bool(session_allowed or sql_link_allowed)
    result['needs_auth'] = not allowed
    if not allowed or (state.get('SolicitudAccion') == 'DESVINCULAR' and state.get('SolicitudEstado') == 'Pendiente'):
        result['QR'] = None
    # Never expose arbitrary persisted URLs in an image src.
    if result['QR'] and not result['QR'].startswith('data:image/png;base64,'):
        result['QR'] = None
    result['ready'] = 'ConnectionRevision' in state
    return result


def start_local_worker(app=None):
    """A SQL applock in run() arbitrates duplicate launches across web processes."""
    global _WORKER_PROC
    target_app = app or current_app
    enabled = os.environ.get('WHATSAPP_MANAGED_WORKER')
    if enabled == '0':
        return False
    local_debug = bool(
        target_app.debug
        and (not has_request_context() or request.remote_addr in ('127.0.0.1', '::1'))
    )
    auto_managed = (
        os.environ.get('WHATSAPP_ENABLED') == '1'
        and os.environ.get('PYTHON_DOTENV_DISABLED') != '1'
        and not target_app.config.get('TESTING')
    ) or bool(os.environ.get('WEBSITE_SITE_NAME'))
    if enabled != '1' and not (enabled is None and (local_debug or auto_managed)):
        return False
    with _WORKER_LOCK:
        if _WORKER_PROC is not None and getattr(_WORKER_PROC, 'poll', lambda: None)() is None:
            return True
        root = Path(target_app.root_path).parent.resolve()
        logs = Path(target_app.instance_path) / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        with (logs / 'whatsapp-worker.log').open('ab') as output:
            proc = subprocess.Popen(
                [sys.executable, str(root / 'scripts/run_whatsapp.py')],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **options,
            )
            if proc is not None and hasattr(proc, 'poll'):
                _WORKER_PROC = proc
    return True


def ensure_worker_supervisor(app):
    """Start a background daemon supervisor so WhatsApp stays connected 24/7 in Azure and local."""
    global _SUPERVISOR_STARTED
    if os.environ.get('WHATSAPP_ENABLED') != '1':
        return
    if os.environ.get('PYTHON_DOTENV_DISABLED') == '1' or app.config.get('TESTING'):
        return
    if os.environ.get('_WHATSAPP_WORKER_PROCESS') == '1':
        return
    with _WORKER_LOCK:
        if _SUPERVISOR_STARTED:
            return
        _SUPERVISOR_STARTED = True

    def _supervisor_loop():
        # Wait 15s before starting WhatsApp so Gunicorn completes binding and passes Azure container health check
        time.sleep(15.0)
        while True:
            try:
                with app.app_context():
                    start_local_worker(app)
                time.sleep(3.0)
                if _WORKER_PROC is None or _WORKER_PROC.poll() is not None:
                    from app.whatsapp.worker import run as run_worker
                    run_worker(app)
            except RuntimeError as exc:
                if 'Ya existe un worker WhatsApp activo' in str(exc):
                    time.sleep(12.0)
                else:
                    time.sleep(3.0)
            except Exception:
                logging.getLogger(__name__).debug('Supervisor WhatsApp en espera', exc_info=True)
                time.sleep(8.0)
            time.sleep(10.0)

    threading.Thread(target=_supervisor_loop, name='whatsapp-supervisor', daemon=True).start()


def apply_unlink(store, transport, state):
    """None means wait for a connection; False means revocation failed."""
    if state.get('Vinculado') and transport.status not in ('Conectado', 'Requiere vinculación'):
        return None
    if transport.status not in ('Conectado', 'Esperando QR', 'Requiere vinculación'):
        return None
    try:
        if transport.status == 'Conectado':
            transport.logout()  # Invalidates remote credentials; stop() alone does not.
    except Exception:
        logging.getLogger(__name__).warning('No se pudo revocar la sesión de WhatsApp; se conservará la cuenta.')
        store.complete_link(state['SolicitudID'], False,
                            'No se pudo desvincular. Compruebe la conexión y vuelva a intentarlo.')
        return False
    transport.stop()
    store.complete_link(state['SolicitudID'], True)
    return True
