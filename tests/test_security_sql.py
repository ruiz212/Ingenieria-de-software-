"""Real regression checks, explicit QA opt-in, only temporary owned records."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pyodbc
import pyotp
import pytest
from app import create_app
from app.models import User
from app.services import auth_challenges as challenges


@pytest.fixture
def security_case():
    value=os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:pytest.skip('Defina TEST_DB_CONNECTION_STRING para una base PanaderiaQA_ aislada.')
    conn=pyodbc.connect(value)
    name=conn.cursor().execute('SELECT DB_NAME()').fetchone()[0]
    assert name.startswith('PanaderiaQA_')
    username='qa_security_'+uuid.uuid4().hex
    phone='+5058'+f'{uuid.uuid4().int%10000000:07d}'
    cursor=conn.cursor()
    role=cursor.execute("SELECT ID FROM Roles WHERE Nombre='Admin'").fetchone()[0]
    uid=cursor.execute('INSERT INTO Usuarios(NombreCompleto,Username,PasswordHash,RolID) OUTPUT INSERTED.ID VALUES(?,?,?,?)',
                       'Synthetic security QA',username,'not-a-login-credential',role).fetchone()[0]
    conn.commit()
    class Config:
        TESTING=True
        SECRET_KEY='qa-security-synthetic-only'
        SQL_SERVER_CONNECTION_STRING=value
    app=create_app(Config)
    try:
        with app.app_context():yield app,conn,uid,phone
    finally:
        conn.rollback()
        cursor=conn.cursor()
        cursor.execute('DELETE FROM AuthChallenges WHERE Subject IN (?,?)',phone,str(uid))
        cursor.execute('DELETE FROM Usuarios WHERE ID=? AND Username=?',uid,username)
        conn.commit()
        conn.close()


def test_sql_sms_consumption_rolls_back_and_can_only_commit_once(security_case):
    app,conn,uid,phone=security_case
    token,code=challenges.issue_sms(phone)
    assert challenges.verify_sms(token,phone,code)
    assert challenges.consume_sms(conn.cursor(),token,phone)
    conn.rollback()
    assert challenges.consume_sms(conn.cursor(),token,phone)
    conn.commit()
    assert not challenges.consume_sms(conn.cursor(),token,phone)
    conn.rollback()


def test_sql_sms_throttle_preserves_first_verification(security_case):
    app,conn,uid,phone=security_case
    token,code=challenges.issue_sms(phone)
    with pytest.raises(challenges.ResendTooSoon):challenges.issue_sms(phone)
    assert challenges.verify_sms(token,phone,code)


def test_sql_sms_parallel_wrong_attempts_cannot_exceed_limit(security_case):
    app,conn,uid,phone=security_case
    token,code=challenges.issue_sms(phone)
    wrong='000001' if code=='000000' else '000000'
    def attempt(_):
        with app.app_context():return challenges.verify_sms(token,phone,wrong)
    with ThreadPoolExecutor(max_workers=4) as pool:assert not any(pool.map(attempt,range(8)))
    assert conn.cursor().execute('SELECT Attempts FROM AuthChallenges WHERE Token=?',token).fetchone()[0]==5
    conn.rollback()
    assert not challenges.verify_sms(token,phone,code)


def test_sql_totp_enrollment_and_reset_invalidate_partial_login(security_case):
    app,conn,uid,phone=security_case
    user=User.get_by_id(uid)
    token=challenges.start_totp(user,enroll=True)
    secret=challenges.pending_totp(token,'totp_enroll')['Secret']
    assert challenges.complete_totp(token,pyotp.TOTP(secret).now(),'totp_enroll')==uid
    enrolled=User.get_by_id(uid)
    assert enrolled.totp_enabled and enrolled.totp_secret==secret
    login=challenges.start_totp(enrolled)
    conn.cursor().execute('UPDATE Usuarios SET TOTPSecret=NULL,TOTPEnabled=0 WHERE ID=?',uid)
    conn.commit()
    assert challenges.complete_totp(login,pyotp.TOTP(secret).now(),'totp_login') is None
    reset=challenges.start_totp(User.get_by_id(uid),enroll=True)
    next_secret=challenges.pending_totp(reset,'totp_enroll')['Secret']
    assert challenges.complete_totp(reset,pyotp.TOTP(next_secret).now(),'totp_enroll')==uid


def test_sql_waste_constraint_rejects_negative_quantity(security_case):
    app,conn,uid,phone=security_case
    cursor=conn.cursor()
    product=cursor.execute('SELECT TOP 1 ID FROM Productos ORDER BY ID').fetchone()[0]
    with pytest.raises(pyodbc.IntegrityError,match='CK_Mermas_CantidadPositiva'):
        cursor.execute("INSERT INTO Mermas(ProductoID,Cantidad,Motivo,UsuarioID) VALUES(?,-1,'Otro',?)",product,uid)
    conn.rollback()


def test_sql_cash_count_preserves_applied_exchange_rate(security_case):
    app,conn,uid,phone=security_case
    from decimal import Decimal
    cursor=conn.cursor()
    shift=cursor.execute('INSERT INTO TurnosCaja(UsuarioID) OUTPUT INSERTED.ID VALUES(?)',uid).fetchone()[0]
    saved=cursor.execute('''INSERT INTO ArqueoCaja
        (TurnoID,UsuarioID,EfectivoContado,TransferenciasContadas,EfectivoSistema,TransferenciasSistema,TipoCambioUsado)
        OUTPUT INSERTED.TipoCambioUsado VALUES(?,?,0,0,0,0,?)''',shift,uid,Decimal('36.624345')).fetchone()[0]
    assert saved==Decimal('36.624345')
    conn.rollback()
