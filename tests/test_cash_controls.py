from decimal import Decimal
from types import SimpleNamespace
import pytest
from flask_wtf.csrf import generate_csrf
from app import create_app
from app.models import User
from app.admin import routes_pos


class CashConnection:
    def __init__(self):self.sql='';self.inserted=None;self.committed=False;self.rate='36.6243';self.mermas=[]
    def cursor(self):return self
    def execute(self,sql,*args):
        self.sql=sql
        if 'INSERT INTO ArqueoCaja' in sql:self.inserted=args
        if 'INSERT INTO Mermas' in sql:self.mermas.append(args)
        return self
    def fetchone(self):
        if 'FROM TurnosCaja' in self.sql:return SimpleNamespace(ID=9001)
        if 'SELECT ID FROM ArqueoCaja' in self.sql:return None
        if 'FROM Pagos p' in self.sql:return SimpleNamespace(EfectivoCordobasSistema=Decimal('3662.43'),EfectivoUSDSistema=0,TransferenciasSistema=0)
        if 'tipo_cambio_usd' in self.sql:return SimpleNamespace(Valor=self.rate)
        if 'umbral_discrepancia' in self.sql:return SimpleNamespace(Valor='50')
        if 'SUM(Total)' in self.sql:return (Decimal('3662.43'),)
        if 'INSERT INTO ArqueoCaja' in self.sql:return (9001,)
        raise AssertionError(self.sql)
    def commit(self):self.committed=True
    def rollback(self):self.inserted=None;self.mermas=[]
    def close(self):pass


@pytest.fixture
def case(monkeypatch):
    class Config:
        TESTING=True
        SECRET_KEY='isolated-cash'
        WTF_CSRF_ENABLED=True
    app=create_app(Config)
    @app.get('/test/csrf')
    def token():return {'token':generate_csrf()}
    db=CashConnection()
    monkeypatch.setattr(routes_pos,'get_db_connection',lambda:db)
    def make(role='Estandar'):
        monkeypatch.setattr(app.login_manager,'_user_callback',lambda _:User(9001,'synthetic','Synthetic',1,role))
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id']='emp_9001';session['_fresh']=True
        return client
    return db,make


def post(client,path,data):
    token=client.get('/test/csrf').json['token']
    return client.post(path,json=data,headers={'X-CSRFToken':token})


@pytest.mark.parametrize('forged_rate',[73.2486,'NaN',-1,0,None])
def test_cash_count_uses_server_rate_and_decimal_rounding(case,forged_rate):
    db,make=case
    response=post(make(),'/admin/api/arqueo/etapa1-conteo',{'efectivo_contado':0,'dolares_contados':50,'transferencias_contadas':0,'tipo_cambio':forged_rate})
    assert response.status_code==200
    assert response.json['arqueo']['efectivo_contado']==1831.22
    assert response.json['arqueo']['diferencia_efectivo']==-1831.21
    assert response.json['arqueo']['requiere_justificacion'] is True
    assert Decimal(str(db.inserted[5]))==Decimal('36.6243')


@pytest.mark.parametrize('rate',['NaN','Infinity','-1','0','invalid'])
def test_invalid_configured_rate_does_not_confirm_cash_count(case,rate):
    db,make=case;db.rate=rate
    response=post(make(),'/admin/api/arqueo/etapa1-conteo',{'efectivo_contado':0,'dolares_contados':50,'transferencias_contadas':0})
    assert response.status_code==400 and not db.committed


@pytest.mark.parametrize('quantity',[-100,0,'1.5',True,'NaN'])
def test_merma_rejects_nonpositive_or_fractional_quantity(case,quantity):
    db,make=case
    response=post(make(),'/admin/api/mermas',{'producto_id':1,'cantidad':quantity,'motivo':'Otro'})
    assert response.status_code==400
    assert db.mermas==[] and not db.committed


def test_positive_merma_is_saved(case):
    db,make=case
    response=post(make(),'/admin/api/mermas',{'producto_id':1,'cantidad':2,'motivo':'Otro'})
    assert response.status_code==200 and db.committed and db.mermas[0][1]==2


def test_unknown_merma_reason_is_validation_error(case):
    db,make=case
    response=post(make(),'/admin/api/mermas',{'producto_id':1,'cantidad':2,'motivo':'Desconocido'})
    assert response.status_code==400 and not db.committed


@pytest.mark.parametrize('role',['Admin','SuperAdmin'])
def test_manual_accepts_canonical_admin_roles(case,role):
    response=case[1](role).get('/admin/manual_admin')
    assert response.status_code==200 and 'manual' in response.text.lower()
