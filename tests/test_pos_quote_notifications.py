"""Quote state and its WhatsApp outbox event must share one transaction."""
from types import SimpleNamespace
from decimal import Decimal
import re
import sqlite3
import pytest
from flask_wtf.csrf import generate_csrf

from app import create_app
from app.models import User
from app.pos import routes
from app.whatsapp import repository


@pytest.fixture
def quotes(tmp_path, monkeypatch):
    path = tmp_path / 'quotes.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE Cotizaciones(ID INTEGER PRIMARY KEY,ClienteID INTEGER,SessionID TEXT,
            Estado TEXT,TelefonoContacto TEXT,PrecioCotizado NUMERIC);
        CREATE TABLE Outbox(QuoteID INTEGER,Estado TEXT,Precio NUMERIC);
        INSERT INTO Cotizaciones VALUES(101,NULL,'private-wa-token','Cotizada','88887777',450);
        ''')
    class Connection:
        def __init__(self):
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
        def cursor(self): return self
        def execute(self, sql, *params):
            sql = re.sub(r'WITH\s*\(UPDLOCK,\s*HOLDLOCK\)', '', sql, flags=re.I)
            self.result = self.db.execute(sql, tuple(str(value) if isinstance(value, Decimal) else value for value in params))
            self.rowcount = self.result.rowcount
            return self
        def fetchone(self):
            row = self.result.fetchone()
            return SimpleNamespace(**dict(row)) if row else None
        def commit(self): self.db.commit()
        def rollback(self): self.db.rollback()
        def close(self): self.db.close()
    class Config:
        TESTING = True
        SECRET_KEY = 'isolated-quote-notifications'
        WTF_CSRF_ENABLED = True
        SQL_SERVER_CONNECTION_STRING = ''
    app = create_app(Config)
    app.login_manager._user_callback = lambda _: User(7, 'synthetic', 'QA', 1, 'Estandar')
    @app.get('/fixture/csrf')
    def csrf(): return {'token': generate_csrf()}
    monkeypatch.setattr(routes, 'get_db_connection', Connection)
    def notify(cursor, kind, identifier, **kwargs):
        assert kind == 'cotizacion'
        cursor.execute('INSERT INTO Outbox SELECT ID,Estado,PrecioCotizado FROM Cotizaciones WHERE ID=?', identifier)
    monkeypatch.setattr(repository, 'notify', notify)
    client = app.test_client()
    with client.session_transaction() as value:
        value['_user_id'] = 'emp_7'
        value['_fresh'] = True
    token = client.get('/fixture/csrf').json['token']
    def post(action, payload=None):
        return client.post('/api/cotizaciones/101/' + action, json=payload or {}, headers={'X-CSRFToken': token})
    def read():
        with sqlite3.connect(path) as db:
            quote = db.execute('SELECT Estado,PrecioCotizado FROM Cotizaciones WHERE ID=101').fetchone()
            outbox = db.execute('SELECT Estado,Precio FROM Outbox').fetchall()
            return quote, outbox
    return post, read, path


@pytest.mark.parametrize('action,payload,state,price', [
    ('cotizar', {'precio': 680}, 'Cotizada', 680),
    ('rechazar', {}, 'Rechazada', 450),
    ('aceptar', {}, 'Aceptada', 450),
])
def test_quote_and_notice_are_committed_together(quotes, action, payload, state, price):
    post, read, _ = quotes
    response = post(action, payload)
    assert response.status_code == 200
    assert read() == ((state, price), [(state, price)])


@pytest.mark.parametrize('action', ['cotizar', 'rechazar', 'aceptar'])
def test_failed_notice_rolls_back_quote_change(quotes, monkeypatch, action):
    post, read, _ = quotes
    def unavailable(*a, **k): raise RuntimeError('synthetic outbox failure')
    monkeypatch.setattr(repository, 'notify', unavailable)
    response = post(action, {'precio': 680} if action == 'cotizar' else {})
    assert response.status_code >= 500
    assert read() == (('Cotizada', 450), [])


def test_accepted_quote_cannot_be_repriced_or_rejected(quotes):
    post, read, path = quotes
    with sqlite3.connect(path) as db:
        db.execute("UPDATE Cotizaciones SET Estado='Aceptada' WHERE ID=101")
    assert post('cotizar', {'precio': 999}).status_code == 409
    assert post('rechazar').status_code == 409
    assert read() == (('Aceptada', 450), [])


def test_quote_notification_uses_only_callers_sql_cursor(monkeypatch):
    monkeypatch.setenv('WHATSAPP_ENABLED', '1')
    calls = []
    class Cursor:
        def execute(self, sql, *args):
            calls.append((sql, args))
            if 'sp_WhatsAppNotificar' not in sql:
                raise AssertionError('POS must not depend on a worker-only metadata procedure')
            return self
    def separate_connection(*a, **k):
        raise AssertionError('Quote notification cannot open another transaction')
    monkeypatch.setattr(repository, 'enqueue_phone_notification', separate_connection)
    repository.notify(Cursor(), 'cotizacion', 101, phone='88887777', estado='Cotizada', precio=680)
    assert calls == [('EXEC crm.sp_WhatsAppNotificar ?,?', ('cotizacion', 101))]


def test_quote_outbox_sql_error_is_not_silenced(monkeypatch):
    monkeypatch.setenv('WHATSAPP_ENABLED', '1')
    class Cursor:
        def execute(self, *args):
            raise RuntimeError('synthetic SQL outbox failure')
    with pytest.raises(RuntimeError, match='outbox failure'):
        repository.notify(Cursor(), 'cotizacion', 101, phone='88887777', estado='Cotizada', precio=680)
