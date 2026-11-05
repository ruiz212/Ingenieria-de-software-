"""Account lifecycle and local process launch; never runs inside the web worker."""
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from flask import current_app, request, session


def public_state(state):
    result = {key: state.get(key) for key in (
        'Estado', 'Activo', 'QR', 'QRExpira', 'Vinculado', 'CuentaTelefono',
        'ConnectionRevision', 'SolicitudAccion', 'SolicitudEstado', 'SolicitudError')}
    grant = session.get('wa_pairing', {})
    allowed = (grant.get('until', 0) > time.time()
               and grant.get('revision') == state.get('ConnectionRevision'))
    result['needs_auth'] = not allowed
    if not allowed or (state.get('SolicitudAccion') == 'DESVINCULAR' and state.get('SolicitudEstado') == 'Pendiente'):
        result['QR'] = None
    # Never expose arbitrary persisted URLs in an image src.
    if result['QR'] and not result['QR'].startswith('data:image/png;base64,'):
        result['QR'] = None
    result['ready'] = 'ConnectionRevision' in state
    return result


def start_local_worker():
    """A SQL applock in run() arbitrates duplicate launches across web processes."""
    enabled = os.environ.get('WHATSAPP_MANAGED_WORKER')
    local_debug = current_app.debug and request.remote_addr in ('127.0.0.1', '::1')
    if enabled != '1' and not (enabled is None and local_debug):
        return False
    root = Path(current_app.root_path).parent.resolve()
    logs = Path(current_app.instance_path) / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    with (logs / 'whatsapp-worker.log').open('ab') as output:
        subprocess.Popen([sys.executable, str(root / 'scripts/run_whatsapp.py')],
                         cwd=root, stdin=subprocess.DEVNULL, stdout=output,
                         stderr=subprocess.STDOUT, close_fds=True, **options)
    return True


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
