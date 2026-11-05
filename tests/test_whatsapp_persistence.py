"""Exercise the repository against real transactions with an isolated SQL adapter.

The adapter translates the small persistence procedure subset, not business SPs.
SQL Server ownership chaining and permissions still require the documented QA run.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace
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
       Modo TEXT DEFAULT 'IA',Revision INTEGER DEFAULT 0,Avisos INTEGER DEFAULT 1,Imagen TEXT,
       UltimaInteraccion TEXT DEFAULT CURRENT_TIMESTAMP,Pendiente TEXT);
    CREATE TABLE crm.WhatsAppInbox(ID INTEGER PRIMARY KEY,SesionID INTEGER,MessageID TEXT,Texto TEXT,Imagen TEXT,
       Estado TEXT DEFAULT 'Pendiente',Intentos INTEGER DEFAULT 0,Creado TEXT DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(SesionID,MessageID));
    CREATE TABLE crm.WhatsAppOutbox(ID INTEGER PRIMARY KEY,SesionID INTEGER,Clave TEXT UNIQUE,Texto TEXT,
       Tipo TEXT,Revision INTEGER,Estado TEXT DEFAULT 'Pendiente',Intentos INTEGER DEFAULT 0,
       Disponible TEXT DEFAULT CURRENT_TIMESTAMP,Creado TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE crm.WhatsAppAcciones(Clave TEXT PRIMARY KEY,SesionID INTEGER,Herramienta TEXT,Resultado TEXT);
    CREATE TABLE crm.Cotizaciones(ID INTEGER PRIMARY KEY,SessionID TEXT,ClienteID INTEGER,Estado TEXT,PrecioCotizado REAL,
       Especificaciones TEXT,FechaEntrega TEXT,RutaImagenReferencia TEXT,TelefonoContacto TEXT,NombreContacto TEXT,
       FechaSolicitud TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE crm.Clientes(ID INTEGER PRIMARY KEY,Nombre TEXT);
    ''')
    sql = (Path(__file__).parents[1] / 'database/06_whatsapp_bot.sql').read_text(encoding='utf-8')
    procedures = dict(re.findall(r'CREATE OR ALTER PROCEDURE crm\.(sp_WhatsApp\w+)\s.*?AS\s*BEGIN\s*SET NOCOUNT ON;\s*(.*?)\nEND;', sql, re.S))
    class Cursor:
        def execute(self, statement, *params):
            name = statement.split()[1].split('.')[-1]
            self.admin_rows = name == 'sp_ObtenerCotizacionesPendientesAdmin'
            if self.admin_rows:
                linking = (Path(__file__).parents[1]/'database/07_whatsapp_vinculacion.sql').read_text(encoding='utf-8')
                query = re.search(r'PROCEDURE crm.sp_ObtenerCotizacionesPendientesAdmin\s+AS\s+BEGIN\s+SET NOCOUNT ON;\s+(SELECT .*?);', linking, re.S)[1]
                self.result = db.execute(query)
                self.description = self.result.description
                return self
            if name == 'sp_WhatsAppCotizacion':
                # Execute the actual INSERT contract; SQL Server guards need the separate QA check.
                assert params[1] == 'crear'
                token, phone, image = db.execute('SELECT Token,Telefono,Imagen FROM crm.WhatsAppSesiones WHERE ID=?', (params[0],)).fetchone()
                query = re.search(r'INSERT crm.Cotizaciones\([^;]+;', sql)[0].rstrip(';')
                query = query.replace('INSERT crm.', 'INSERT INTO crm.').replace('OUTPUT INSERTED.ID', '')+' RETURNING ID'
                self.result = db.execute(query, dict(Token=token, Telefono=phone, Imagen=image, Nombre=params[3], Detalle=params[4], Fecha=params[5]))
                self.description = self.result.description
                return self
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
        def fetchall(self):
            values = self.result.fetchall()
            if not self.admin_rows:
                return values
            result = []
            for value in values:
                row = dict(zip([c[0] for c in self.description], value))
                for key in ('FechaEntrega', 'FechaSolicitud'):
                    row[key] = datetime.fromisoformat(row[key]) if row[key] else None
                result.append(SimpleNamespace(**row))
            return result
    @contextmanager
    def connect(worker=False):
        try:
            yield db, Cursor()
            db.commit()
        except Exception:
            db.rollback()
            raise
    monkeypatch.setattr(repository, 'connection', connect)
    from app.pos import routes as pos_routes
    monkeypatch.setattr(pos_routes, 'get_db_connection', lambda: SimpleNamespace(cursor=Cursor, close=lambda: None))
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
    db.execute("INSERT INTO crm.Cotizaciones(ID,SessionID,ClienteID,Estado,PrecioCotizado) SELECT 42,Token,NULL,'Cotizada',450 FROM crm.WhatsAppSesiones")
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


def test_confirmed_whatsapp_quote_appears_in_the_shared_pos_inbox_once(store, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager
    from app.models import User
    from app.pos import pos_bp
    from app.whatsapp.tools import Tools
    channel, db = store
    channel.receive('50588888888@s.whatsapp.net', '+50588888888', 'request', 'cotizar', 'uploads/referencias/synthetic.jpg')
    db.execute("UPDATE crm.WhatsAppSesiones SET Imagen='uploads/referencias/synthetic.jpg'")
    db.commit()
    Tools(channel, {'id': 1, 'Revision': 0}).call('agendar_cotizacion_pastel', {
        'nombre': 'Cliente de WhatsApp', 'especificaciones': 'Pastel para 20 personas',
        'fecha_entrega': (datetime.now()+timedelta(days=3)).isoformat(), 'confirmed': True}, 'draft')
    assert db.execute('SELECT COUNT(*) FROM crm.Cotizaciones').fetchone()[0] == 0
    pending = db.execute('SELECT Pendiente FROM crm.WhatsAppSesiones').fetchone()[0]
    item = {'id': 1, 'ID': 2, 'Revision': 0, 'Texto': 'CONFIRMAR', 'Pendiente': pending}
    assert channel.command(item)[0]
    channel.command(item)  # Duplicate native delivery cannot create a second quote.
    assert db.execute('SELECT COUNT(*) FROM crm.Cotizaciones').fetchone()[0] == 1
    app = Flask(__name__)
    app.secret_key = 'synthetic'
    LoginManager(app).user_loader(lambda uid: User(7, 'synthetic', 'Admin', 1, 'Admin'))
    app.register_blueprint(pos_bp)
    monkeypatch.setattr('app.db.is_sqlserver_cursor', lambda cur: True)
    client = app.test_client()
    with client.session_transaction() as value:
        value['_user_id'] = 'emp_7'
    response = client.get('/api/cotizaciones/pendientes')
    assert response.status_code == 200
    assert response.json[0] | {'fecha_solicitud': ''} == {
        'id': 1, 'cliente': 'Cliente de WhatsApp', 'telefono': '+50588888888',
        'especificaciones': 'Pastel para 20 personas', 'fecha_entrega': (datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d'),
        'ruta_imagen': 'uploads/referencias/synthetic.jpg', 'estado': 'Pendiente', 'precio_cotizado': None,
        'fecha_solicitud': '', 'canal': 'WhatsApp'}


def test_quote_and_order_notifications_work_with_associated_phone_number(store, monkeypatch):
    channel, db = store
    monkeypatch.setenv('WHATSAPP_ENABLED', '1')
    dummy_cursor = SimpleNamespace(execute=lambda *a, **kw: None, fetchone=lambda: None)
    # 1. Quote priced notification to a phone number that hasn't even chatted before
    repository.notify(
        dummy_cursor, 'cotizacion', 15,
        phone='8765-4321', estado='Cotizada', precio=680.0, fecha_entrega='12/11/2026',
    )
    session_row = db.execute("SELECT ID, Telefono, Avisos FROM crm.WhatsAppSesiones WHERE Telefono='+50587654321'").fetchone()
    assert session_row is not None and session_row[2] == 1
    outbox = db.execute("SELECT Clave, Texto, Tipo FROM crm.WhatsAppOutbox WHERE SesionID=?", (session_row[0],)).fetchall()
    assert len(outbox) == 1
    assert 'COT-0015' in outbox[0][1] and '680' in outbox[0][1] and outbox[0][2] == 'Aviso'

    # 2. Order status changes (Pendiente -> En Proceso -> Listo -> Entregado) on associated phone
    for state in ('Pendiente', 'En Proceso', 'Listo', 'Entregado'):
        repository.notify(
            dummy_cursor, 'pedido', 99,
            phone='+505 8765 4321', estado=state,
            numero_factura='FAC-0099', codigo_seguimiento='SEG99XYZ',
            fecha_entrega='15/11/2026', saldo=250.0,
        )
    order_msgs = db.execute(
        "SELECT Clave, Texto FROM crm.WhatsAppOutbox WHERE SesionID=? AND Clave LIKE 'order:99:%' ORDER BY ID",
        (session_row[0],),
    ).fetchall()
    assert [m[0] for m in order_msgs] == [
        'order:99:Pendiente',
        'order:99:En Proceso',
        'order:99:Listo',
        'order:99:Entregado',
    ]
    assert all('FAC-0099' in m[1] for m in order_msgs)
