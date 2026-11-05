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
from app.whatsapp.repository import Store
from app.whatsapp.tools import Tools


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
    store, agent = Store(), Agent(Gemini())
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
            last_send, last_heartbeat = 0, 0
            state = store.state(transport.status)
            while connector.is_alive():
                cur.execute('EXEC crm.sp_WhatsAppPing')  # Do not continue if singleton ownership is lost.
                cur.fetchone()
                if time.monotonic() - last_heartbeat >= 10:
                    state = store.state(transport.status, transport.qr)
                    last_heartbeat = time.monotonic()
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
                    if transport.status == 'Conectado' and time.monotonic() - last_send >= 2:
                        outgoing = store.outgoing()
                        if outgoing:
                            store.deliver(outgoing, transport.send)
                            last_send = time.monotonic()
                time.sleep(0.5)
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
