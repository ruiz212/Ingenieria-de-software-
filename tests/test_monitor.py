"""Pedidos sintéticos; nunca se usa el primer encargo ni un usuario de la BD."""
from copy import deepcopy
from decimal import Decimal
import pytest
from flask_wtf.csrf import generate_csrf
from app import create_app
from app.models import User,Cliente
from app.monitor import routes
from app.services.contabilidad_service import ContabilidadService,ContabilidadError


class OrderDatabase:
    def __init__(self):
        self.saved={'state':'Pendiente','payments':[Decimal('50')],'journal':[]}
        self.pending=None
        self.result=None
        self.rowcount=1
        self.commits=0
        self.rollbacks=0
    def cursor(self):
        self.pending=deepcopy(self.saved)
        return self
    def execute(self,sql,*args):
        self.result=None
        if 'SELECT e.Estado' in sql:
            self.result=(self.pending['state'],90001,'SYNTHETIC',Decimal('100'),'Emitida')
        elif 'UPDATE e SET Estado' in sql:
            self.rowcount=int(self.pending['state']==args[2])
            if self.rowcount:self.pending['state']=args[0]
        elif 'SUM(Monto)' in sql:
            self.result=(sum(self.pending['payments']),)
        elif 'INSERT INTO Pagos' in sql:self.pending['payments'].append(args[2])
        elif 'INSERT INTO BitacoraFiscal' in sql:pass
        elif 'SELECT ID FROM TurnosCaja' in sql:self.result=(7,)
        elif 'SELECT ID FROM ArqueoCaja' in sql:self.result=None
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:self.result=(1,)
        else:assert 'CodigoSeguimiento = ?' in sql,sql
        return self
    def fetchone(self):return self.result
    def commit(self):self.saved=deepcopy(self.pending);self.commits+=1
    def rollback(self):self.pending=None;self.rollbacks+=1
    def close(self):self.pending=None


@pytest.fixture
def monitor_case(monkeypatch):
    class Config:
        TESTING=True
        SECRET_KEY='isolated-monitor-tests'
        WTF_CSRF_ENABLED=True
    app=create_app(Config)
    @app.get('/test/csrf')
    def csrf_token():return {'token':generate_csrf()}
    db=OrderDatabase()
    monkeypatch.setattr(routes,'get_db_connection',lambda:db)
    monkeypatch.setattr(routes,'cargar_encargos',lambda cursor:[{'codigo_seguimiento':'SYNTHETIC','encargo_detalles':{'estado':db.saved['state']}}])
    def book(cursor,*args,**kwargs):cursor.pending['journal'].append(Decimal(str(args[2])))
    monkeypatch.setattr(ContabilidadService,'contabilizar_cobro_encargo',book)
    def client_for(role=None):
        client=app.test_client()
        if role:
            actor=Cliente(90001,'Synthetic','Guest','00000000',role=='Invitado',1) if role in ('Invitado','Cliente') else User(90001,'synthetic','Synthetic',1,role)
            monkeypatch.setattr(app.login_manager,'_user_callback',lambda _:actor)
            with client.session_transaction() as session:
                session['_user_id']=actor.get_id();session['_fresh']=True
        return client
    return app,db,client_for


def put_state(client,state):
    token=client.get('/test/csrf').json['token']
    return client.put('/api/seguimiento/SYNTHETIC/estado',json={'estado':state},headers={'X-CSRFToken':token})


def test_monitor_requires_login(monitor_case):
    response=monitor_case[2]().get('/monitor')
    assert response.status_code==302 and '/login' in response.location


@pytest.mark.parametrize('role',['Admin','SuperAdmin','Operativo','Estandar'])
def test_internal_roles_can_read_and_update(monitor_case,role):
    app,db,make=monitor_case
    client=make(role)
    assert client.get('/monitor').status_code==200
    assert client.get('/api/monitor/pedidos').json['encargos'][0]['codigo_seguimiento']=='SYNTHETIC'
    assert put_state(client,'En Proceso').status_code==200
    assert db.saved['state']=='En Proceso'


@pytest.mark.parametrize('role',['Invitado','Cliente'])
def test_customer_cannot_read_or_change_internal_orders(monitor_case,role):
    app,db,make=monitor_case
    client=make(role)
    assert client.get('/monitor').status_code==302
    assert client.get('/api/monitor/pedidos').status_code==403
    assert put_state(client,'Entregado').status_code==403
    assert db.saved['state']=='Pendiente' and db.commits==0


def test_delivery_rolls_back_state_and_payment_when_accounting_fails(monitor_case,monkeypatch):
    app,db,make=monitor_case
    client=make('Admin')
    def fail(*a,**k):raise ContabilidadError('Período cerrado sintético')
    monkeypatch.setattr(ContabilidadService,'contabilizar_cobro_encargo',fail)
    response=put_state(client,'Entregado')
    assert response.status_code==409
    assert db.saved=={'state':'Pendiente','payments':[Decimal('50')],'journal':[]}
    assert db.commits==0 and db.rollbacks==1


def test_delivery_books_only_outstanding_balance_and_retry_is_idempotent(monitor_case):
    app,db,make=monitor_case
    client=make('Admin')
    assert put_state(client,'Entregado').status_code==200
    assert db.saved=={'state':'Entregado','payments':[Decimal('50'),Decimal('50')],'journal':[Decimal('50')]}
    assert put_state(client,'Entregado').status_code==200
    assert len(db.saved['payments'])==2 and len(db.saved['journal'])==1


def test_public_tracking_of_unknown_code_still_works_without_login(monitor_case):
    response=monitor_case[2]().get('/seguimiento/SYNTHETIC-UNKNOWN')
    assert response.status_code==200
    assert 'no corresponde a ninguna factura' in response.text or 'Encargo no encontrado' in response.text
