"""One SQL-locked process per account. A supervisor restarts on fatal DB failure."""
import logging
import os
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pyodbc
from app.db import get_db_connection
from app.whatsapp.agent import Agent, Gemini
from app.whatsapp.client import Transport
from app.whatsapp.repository import Store, WAKE_EVENT
from app.whatsapp.tools import Tools
from app.whatsapp.linking import apply_unlink


class LazyAgent:
    """Pairing and manual replies do not depend on an inference credential."""
    def __init__(self):
        self.agent = None

    def reply(self, *args):
        if self.agent is None:
            try:
                self.agent = Agent(Gemini())
            except ValueError:
                return 'El asistente no está disponible. Escribe HUMANO para que te atienda el equipo.'
        return self.agent.reply(*args)


def process(store, agent, item):
    if item['Modo'] == 'HUMANO' and item['Texto'].strip().upper() not in ('AVISOS SI', 'AVISOS SÍ', 'AVISOS NO'):
        store.finish(item, None)
        return
    try:
        handled, response = store.command(item)
    except (ValueError, PermissionError):
        store.finish(item, 'No se pudo confirmar la operación. Revisa los datos o escribe HUMANO.')
        return
    except pyodbc.Error as exc:
        if '52026' not in str(exc):
            raise
        store.finish(item, 'La cotización no está disponible para esta operación. Escribe HUMANO si necesitas ayuda.')
        return
    if not handled:
        response = None if item['Modo'] != 'IA' else agent.reply(
            item['Texto'], store.history(item['id']), Tools(store, item), str(item['ID']))
    store.finish(item, response)


def run(app):
    if os.environ.get('WHATSAPP_ENABLED') != '1':
        raise ValueError('Defina WHATSAPP_ENABLED=1 después de instalar la migración.')
    store, agent = Store(), LazyAgent()
    with app.app_context():
        # Session-owned applock survives commits. Lost connection stops all processing.
        lock = get_db_connection(inject_context=False, apply_role=False)
        transport = connector = executor = None
        owned = False
        try:
            cur = lock.cursor()
            cur.execute('EXEC crm.sp_WhatsAppBloquearWorker')
            if cur.fetchone()[0] < 0:
                raise RuntimeError('Ya existe un worker WhatsApp activo.')
            lock.commit()
            owned = True
            path = Path(os.environ.get('WHATSAPP_SESSION_PATH', str(Path(app.instance_path) / 'whatsapp_session.sqlite3'))).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            transport = Transport(app, store, path)
            connector = threading.Thread(target=transport.connect, daemon=True)
            connector.start()
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='whatsapp-inference')
            pending = None
            last_send, last_heartbeat = 0.0, 0.0
            waiting_unlink = None
            state = store.state(transport.status, transport.qr)
            active_link_request = state.get('SolicitudID')
            while True:
                WAKE_EVENT.clear()
                if connector is not None and not connector.is_alive() and transport.status != 'Requiere vinculación':
                    if state.get('SolicitudEstado') == 'Pendiente' and state.get('SolicitudAccion') == 'VINCULAR' and not state.get('Vinculado'):
                        transport = None
                    else:
                        break
                cur.execute('EXEC crm.sp_WhatsAppPing')  # Do not continue if singleton ownership is lost.
                cur.fetchone()
                now = time.monotonic()
                if transport is not None and transport.status == 'Esperando QR' and getattr(transport, 'qr_updated_at', 0) and now - transport.qr_updated_at > 70:
                    transport.status, transport.qr, transport.qr_updated_at = 'Desconectado', None, 0.0
                if now - last_heartbeat >= 2:
                    state = store.state(transport.status if transport else 'Sin vincular', transport.qr if transport else None)
                    last_heartbeat = now
                if transport is None:
                    if state.get('SolicitudEstado') == 'Pendiente' and state.get('SolicitudAccion') == 'VINCULAR':
                        transport = Transport(app, store, path)
                        connector = threading.Thread(target=transport.connect, daemon=True)
                        connector.start()
                        active_link_request = state.get('SolicitudID')
                    elif state.get('SolicitudEstado') == 'Pendiente' and state.get('SolicitudAccion') == 'DESVINCULAR':
                        # This process already revoked the previous native session.
                        store.complete_link(state['SolicitudID'], True)
                        state = store.state('Sin vincular')
                        continue
                    else:
                        WAKE_EVENT.wait(0.2)
                        continue
                if state.get('SolicitudEstado') == 'Pendiente':
                    if state.get('SolicitudAccion') == 'DESVINCULAR':
                        waiting_unlink = waiting_unlink or time.monotonic()
                        # Finish in-flight SQL work before revoking this account.
                        if pending is None or pending.done():
                            removed = apply_unlink(store, transport, state)
                            if removed is True:
                                connector.join(timeout=10)
                                if connector.is_alive():
                                    raise RuntimeError('La conexión anterior no terminó; reinicie el servicio antes de vincular otra cuenta.')
                                # Retain the singleton process, ready for an explicit new pairing.
                                transport = connector = None
                                state = store.state('Sin vincular')
                                waiting_unlink = None
                                continue
                            if removed is False or time.monotonic() - waiting_unlink > 60:
                                if removed is not False:
                                    store.complete_link(state['SolicitudID'], False,
                                        'La cuenta no pudo reconectarse para desvincular. Revise la conexión y reintente.')
                                state = store.state(transport.status, transport.qr)
                                waiting_unlink = None
                        WAKE_EVENT.wait(0.2)
                        continue
                    if state.get('SolicitudAccion') == 'VINCULAR':
                        if transport.status == 'Conectado':
                            store.complete_link(state['SolicitudID'], True)
                            active_link_request = state.get('SolicitudID')
                        elif not state.get('Vinculado'):
                            stale_unlinked = (
                                transport.status in ('Desconectado', 'Requiere vinculación')
                                and getattr(transport, 'started_at', 0)
                                and time.monotonic() - transport.started_at > 20
                            )
                            if state.get('SolicitudID') != active_link_request or stale_unlinked:
                                transport.stop()
                                if connector is not None:
                                    connector.join(timeout=5)
                                transport = Transport(app, store, path)
                                connector = threading.Thread(target=transport.connect, daemon=True)
                                connector.start()
                                active_link_request = state.get('SolicitudID')
                if state['Activo']:
                    if pending is not None and pending.done():
                        try:
                            pending.result()
                        except Exception:
                            logging.getLogger(__name__).exception('No se pudo procesar un mensaje WhatsApp')
                        pending = None
                    if pending is None:
                        item = store.next_message()
                        if item:
                            pending = executor.submit(_process_in_context, app, store, agent, item)
                            pending.add_done_callback(lambda _: WAKE_EVENT.set())
                    if transport.status == 'Conectado' and time.monotonic() - last_send >= 0.35:
                        outgoing = store.outgoing()
                        if outgoing:
                            store.deliver(outgoing, transport.send)
                            last_send = time.monotonic()
                            WAKE_EVENT.set()
                WAKE_EVENT.wait(0.15)
        finally:
            try:
                if transport is not None:
                    transport.stop()
            finally:
                try:
                    # Hold singleton ownership until the in-flight transaction finishes.
                    if executor is not None:
                        executor.shutdown(wait=True, cancel_futures=True)
                    if connector is not None:
                        connector.join(timeout=10)
                    if owned:
                        store.state('Desconectado')
                finally:
                    lock.close()
        raise RuntimeError('Finalizó la conexión WhatsApp. Reinicie con el supervisor.')


def _process_in_context(app, store, agent, item):
    with app.app_context():
        process(store, agent, item)
