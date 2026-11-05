"""Worker lifecycle tests use synthetic transports and SQL handles only."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from contextlib import nullcontext
from app.whatsapp.client import Transport
from app.whatsapp import worker


def test_transport_stop_cancels_native_context():
    transport = Transport.__new__(Transport)
    transport.client = SimpleNamespace(stop=Mock(), disconnect=Mock())
    transport.stop()
    transport.client.stop.assert_called_once()


def test_slow_inference_does_not_stop_heartbeat_or_human_delivery(monkeypatch, tmp_path):
    started, healthy, finished, disconnected = [threading.Event() for _ in range(4)]
    delivered = []
    class Cursor:
        def execute(self, *args): return self
        def fetchone(self): return (0,)
    connection = SimpleNamespace(cursor=Cursor, commit=lambda: None, close=Mock())
    class Store:
        issued = False
        def state(self, *args):
            if started.is_set() and not finished.is_set(): healthy.set()
            return {'Activo': True}
        def next_message(self):
            if not self.issued:
                self.issued = True
                return {'ID': 1}
        def outgoing(self):
            return {'ID': 2} if started.is_set() and not delivered else None
        def deliver(self, outgoing, send): delivered.append(outgoing['ID'])
    class FakeTransport:
        status, qr = 'Conectado', None
        def __init__(self, *args): pass
        def connect(self): disconnected.wait(3)
        def stop(self): disconnected.set()
        def send(self, *args): pass
    def slow_process(*args):
        started.set()
        healthy.wait(1)
        finished.set()
        disconnected.set()
    monotonic = iter(range(0, 100000, 11))
    monkeypatch.setenv('WHATSAPP_ENABLED', '1')
    monkeypatch.setenv('WHATSAPP_SESSION_PATH', str(tmp_path/'synthetic.sqlite3'))
    monkeypatch.setattr(worker, 'Store', Store)
    monkeypatch.setattr(worker, 'Gemini', lambda: None)
    monkeypatch.setattr(worker, 'Transport', FakeTransport)
    monkeypatch.setattr(worker, 'get_db_connection', lambda **kwargs: connection)
    monkeypatch.setattr(worker, 'process', slow_process)
    monkeypatch.setattr(worker.time, 'monotonic', lambda: next(monotonic))
    app = SimpleNamespace(app_context=nullcontext, instance_path=str(tmp_path))
    try:
        worker.run(app)
    except RuntimeError:
        pass
    assert healthy.is_set(), 'No heartbeat while inference was running'
    assert delivered == [2], 'Human response was delayed by inference'
    connection.close.assert_called_once()
