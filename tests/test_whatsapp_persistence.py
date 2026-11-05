"""Exercise the repository against real transactions with an isolated SQL adapter.

The adapter translates the small persistence procedure subset, not business SPs.
SQL Server ownership chaining and permissions still require the documented QA run.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import pytest
from app.whatsapp import repository


@pytest.fixture
def store(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.execute("ATTACH DATABASE ':memory:' AS crm")
    db.executescript('''
    CREATE TABLE crm.WhatsAppControl(ID INTEGER PRIMARY KEY,Activo INTEGER);
    INSERT INTO crm.WhatsAppControl VALUES(1,1);
    CREATE TABLE crm.WhatsAppSesiones(ID INTEGER PRIMARY KEY,JID TEXT UNIQUE,Telefono TEXT,Token TEXT,
       Modo TEXT DEFAULT 'IA',Revision INTEGER DEFAULT 0,Avisos INTEGER DEFAULT 0,Imagen TEXT,
       UltimaInteraccion TEXT DEFAULT CURRENT_TIMESTAMP,Pendiente TEXT);
    CREATE TABLE crm.WhatsAppInbox(ID INTEGER PRIMARY KEY,SesionID INTEGER,MessageID TEXT,Texto TEXT,Imagen TEXT,
       Estado TEXT DEFAULT 'Pendiente',Intentos INTEGER DEFAULT 0,Creado TEXT DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(SesionID,MessageID));
    CREATE TABLE crm.WhatsAppOutbox(ID INTEGER PRIMARY KEY,SesionID INTEGER,Clave TEXT UNIQUE,Texto TEXT,
       Tipo TEXT,Revision INTEGER,Estado TEXT DEFAULT 'Pendiente',Intentos INTEGER DEFAULT 0,
       Disponible TEXT DEFAULT CURRENT_TIMESTAMP,Creado TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE crm.WhatsAppAcciones(Clave TEXT PRIMARY KEY,SesionID INTEGER,Herramienta TEXT,Resultado TEXT);
    CREATE TABLE crm.Cotizaciones(ID INTEGER PRIMARY KEY,SessionID TEXT,ClienteID INTEGER,Estado TEXT,PrecioCotizado REAL);
    ''')
    sql = (Path(__file__).parents[1] / 'database/06_whatsapp_bot.sql').read_text(encoding='utf-8')
    procedures = dict(re.findall(r'CREATE OR ALTER PROCEDURE crm\.(sp_WhatsApp\w+)\s.*?AS\s*BEGIN\s*SET NOCOUNT ON;\s*(.*?)\nEND;', sql, re.S))
    class Cursor:
        def execute(self, statement, *params):
            name = statement.split()[1].split('.')[-1]
            query = procedures[name].rstrip(';')
            query = re.sub(r'^INSERT ', 'INSERT INTO ', query)
            bound = []
            def parameter(match):
                bound.append(params[int(match[1])-1])
                return '?'
            query = re.sub(r'@P(\d+)', parameter, query)
            query = re.sub(r' WITH\(UPDLOCK,HOLDLOCK\)', '', query)
            query = query.replace('SYSUTCDATETIME()', 'CURRENT_TIMESTAMP')
            query = query.replace('DATEADD(minute,-1,CURRENT_TIMESTAMP)', "datetime('now','-1 minute')")
            if 'OUTPUT INSERTED.ID' in query:
                query = query.replace('OUTPUT INSERTED.ID', '') + ' RETURNING ID'
            self.result = db.execute(query, bound)
            self.description = self.result.description
            return self
        def fetchone(self): return self.result.fetchone()
        def fetchall(self): return self.result.fetchall()
    @contextmanager
    def connect(worker=False):
        try:
            yield db, Cursor()
            db.commit()
        except Exception:
            db.rollback()
            raise
    monkeypatch.setattr(repository, 'connection', connect)
    yield repository.Store(), db
    db.close()


def test_duplicate_delivery_creates_one_inbox_record(store):
    channel, db = store
    assert channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'one', 'hola')
    assert not channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'one', 'hola repetida')
    assert db.execute('SELECT COUNT(*) FROM crm.WhatsAppInbox').fetchone()[0] == 1


def test_rate_limit_is_persistent_across_repository_instances(store):
    channel, db = store
    for i in range(6):
        assert channel.receive('50588888888@s.whatsapp.net', '+50588888888', str(i), 'hola')
    assert not repository.Store().receive('50588888888@s.whatsapp.net', '+50588888888', 'seven', 'hola')
    assert db.execute('SELECT COUNT(*) FROM crm.WhatsAppInbox').fetchone()[0] == 6


def test_arriving_photo_cannot_change_an_order_currently_being_confirmed(store):
    channel, db = store
    channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'photo', 'otra foto', 'uploads/referencias/new.jpg')
    assert db.execute('SELECT Imagen FROM crm.WhatsAppSesiones').fetchone()[0] is None
    assert db.execute('SELECT Imagen FROM crm.WhatsAppInbox').fetchone()[0] == 'uploads/referencias/new.jpg'


def test_draft_requires_separate_confirmation_message(store):
    channel, db = store
    channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'one', 'aceptar')
    db.execute("INSERT INTO crm.Cotizaciones SELECT 42,Token,NULL,'Cotizada',450 FROM crm.WhatsAppSesiones")
    db.commit()
    result = channel.tool({'id': 1, 'Revision': 0}, 'responder_cotizacion',
                          {'cotizacion_id': 42, 'decision': 'aceptar', 'confirmed': True}, 'one:0')
    assert 'requiere_confirmacion' in result
    assert 'C$ 450' in result['mensaje']
    assert '42' in db.execute('SELECT Pendiente FROM crm.WhatsAppSesiones').fetchone()[0]
    assert db.execute('SELECT COUNT(*) FROM crm.WhatsAppAcciones').fetchone()[0] == 1


def test_handoff_cancels_inflight_tool_even_if_model_has_old_session(store):
    channel, db = store
    channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'one', 'hola')
    db.execute("UPDATE crm.WhatsAppSesiones SET Modo='HUMANO',Revision=1")
    db.commit()
    with pytest.raises(PermissionError):
        channel.tool({'id': 1, 'Revision': 0}, 'consultar_mis_cotizaciones', {}, 'one:0')
    assert db.execute('SELECT COUNT(*) FROM crm.WhatsAppAcciones').fetchone()[0] == 0
