"""Authorization exercised against actual queries on an isolated SQL adapter."""
from datetime import datetime
import re
import sqlite3
from types import SimpleNamespace
import pytest
from flask_wtf.csrf import generate_csrf
from app import create_app
from app.models import Cliente
from app.pos import routes


class QuoteConnection:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('''CREATE TABLE Cotizaciones(ID INTEGER PRIMARY KEY,ClienteID INTEGER,SessionID TEXT,
            Especificaciones TEXT,FechaEntrega TEXT,RutaImagenReferencia TEXT,Estado TEXT,PrecioCotizado REAL,
            TelefonoContacto TEXT,FechaSolicitud TEXT,NombreContacto TEXT)''')
        for id,owner,token,phone in [(42,88,'victim-secret','88888888'),(43,None,'own-token','88888888'),(44,88,'own-token','77777777')]:
            self.db.execute("INSERT INTO Cotizaciones VALUES(?,?,?,?,?,?,'Cotizada',450,?,?,?)",(id,owner,token,'private '+str(id),'2026-12-01',None,phone,'2026-10-17','Synthetic'))
        self.db.commit()
    def cursor(self):return self
    def execute(self,sql,*args):
        sql=re.sub(r'WITH\s*\(UPDLOCK,\s*HOLDLOCK\)','',sql,flags=re.I).replace('SET NOCOUNT ON; ','')
        output='OUTPUT INSERTED.ID' in sql
        if output:sql=sql.replace('OUTPUT INSERTED.ID','')+' RETURNING ID'
        self.result=self.db.execute(sql,args)
        self.rowcount=self.result.rowcount
        return self
    def row(self,value):
        if value is None:return None
        result=dict(value)
        for key in ['FechaEntrega','FechaSolicitud']:
            if result.get(key):result[key]=datetime.fromisoformat(result[key])
        # Creation's OUTPUT consumes an index, authorization consumes attributes.
        return tuple(result.values()) if list(result)==['ID'] else SimpleNamespace(**result)
    def fetchone(self):return self.row(self.result.fetchone())
    def fetchall(self):return [self.row(row) for row in self.result.fetchall()]
    def commit(self):self.db.commit()
    def rollback(self):self.db.rollback()
    def close(self):pass


@pytest.fixture
def case(monkeypatch):
    class Config:
        TESTING=True
        SECRET_KEY='synthetic-quotes-only'
        WTF_CSRF_ENABLED=True
    app=create_app(Config)
    @app.get('/test/csrf')
    def csrf_token():return {'token':generate_csrf()}
    db=QuoteConnection()
    monkeypatch.setattr(routes,'get_db_connection',lambda:db)
    def make(registered=False):
        actor=Cliente(666,'Synthetic','Customer','88888888',not registered,1)
        monkeypatch.setattr(app.login_manager,'_user_callback',lambda _:actor)
        client=app.test_client()
        with client.session_transaction() as session:
            session['_user_id']=actor.get_id();session['_fresh']=True
            session['cotizacion_session_id']='own-token'
            session['cotizacion_telefono']='88888888'
        return client
    yield db,make
    db.db.close()


def post(client,path,payload):
    token=client.get('/test/csrf').json['token']
    return client.post(path,json=payload,headers={'X-CSRFToken':token})


@pytest.mark.parametrize('registered',[False,True])
def test_matching_phone_does_not_list_or_claim_other_customer_quotes(case,registered):
    db,make=case
    response=make(registered).get('/api/cotizaciones/cliente')
    assert response.status_code==200
    assert [row['id'] for row in response.json]==[43]
    assert db.db.execute('SELECT ClienteID FROM Cotizaciones WHERE ID=42').fetchone()[0]==88


@pytest.mark.parametrize('registered',[False,True])
@pytest.mark.parametrize('action',['aceptar','rechazar'])
@pytest.mark.parametrize('quote_id',[42,44])
def test_phone_or_old_session_cannot_change_assigned_foreign_quote(case,registered,action,quote_id):
    db,make=case
    response=post(make(registered),f'/api/cotizaciones/{quote_id}/{action}',{})
    assert response.status_code==403
    assert db.db.execute('SELECT Estado FROM Cotizaciones WHERE ID=?',(quote_id,)).fetchone()[0]=='Cotizada'


@pytest.mark.parametrize('registered',[False,True])
def test_owner_session_can_accept_own_unassigned_quote(case,registered):
    db,make=case
    response=post(make(registered),'/api/cotizaciones/43/aceptar',{})
    assert response.status_code==200
    assert db.db.execute('SELECT Estado FROM Cotizaciones WHERE ID=43').fetchone()[0]=='Aceptada'


def test_creation_with_victim_phone_does_not_grant_victim_access(case):
    db,make=case
    client=make()
    response=post(client,'/api/cotizaciones',{'especificaciones':'Own request','telefono':'88888888','fecha_entrega':'2026-12-01'})
    assert response.status_code==200
    ids=[row['id'] for row in client.get('/api/cotizaciones/cliente').json]
    assert 42 not in ids and 44 not in ids and 43 in ids
