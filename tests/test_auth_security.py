"""Authentication regressions with database/SMS boundaries isolated."""
from io import BytesIO
from types import SimpleNamespace
import re
import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.models import User, Cliente


@pytest.fixture(autouse=True)
def no_real_sql(monkeypatch):
    import pyodbc
    def blocked(*args, **kwargs):
        raise AssertionError('Real SQL is forbidden in authentication unit tests')
    monkeypatch.setattr(pyodbc, 'connect', blocked)


@pytest.fixture
def auth_app(tmp_path, monkeypatch):
    from app.auth import routes

    class Config:
        TESTING = True
        SECRET_KEY = 'isolated-auth-test-key'
        WTF_CSRF_ENABLED = False
        MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    application = create_app(Config)
    application.static_folder = str(tmp_path / 'static')
    monkeypatch.setattr(routes.Cliente, 'get_by_telefono', lambda _: (None, None))
    return application


def registration(**extra):
    return dict(nombre='QA', apellidos='Cliente', telefono='+50588887777',
                password='a-good-test-password', **extra)


def test_registration_rejects_missing_server_sms_verification(auth_app, monkeypatch):
    from app.auth import routes
    writes = []
    conn = SimpleNamespace(cursor=lambda: SimpleNamespace(execute=lambda *args: writes.append(args)),
                           commit=lambda: None, close=lambda: None)
    monkeypatch.setattr(routes, 'get_db_connection', lambda: conn)
    response = auth_app.test_client().post('/cliente/registro', data=registration())
    assert response.status_code == 400
    assert not writes


def test_missing_twilio_credentials_never_discloses_otp(auth_app, monkeypatch):
    monkeypatch.delenv('TWILIO_ACCOUNT_SID', raising=False)
    monkeypatch.delenv('TWILIO_AUTH_TOKEN', raising=False)
    client = auth_app.test_client()
    response = client.post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    assert response.status_code == 503
    assert 'dev_codigo' not in response.json
    with client.session_transaction() as cookie:
        assert not {'sms_code', 'sms_phone', 'telefono_verificado'} & cookie.keys()


def test_mandatory_totp_without_secret_starts_restricted_enrollment(auth_app, sql_state, monkeypatch):
    from app.auth import routes
    user = User(4, 'qa', 'QA', 1, 'SuperAdmin')
    monkeypatch.setattr(routes.User, 'get_by_username', lambda _: (user, generate_password_hash('password')))
    monkeypatch.setattr(routes, 'totp_is_required', lambda: True)
    client = auth_app.test_client()
    response = client.post('/login', data={'identificador': 'qa', 'password': 'password'})
    assert response.location.endswith('/login/totp/enroll')
    with client.session_transaction() as cookie:
        assert '_user_id' not in cookie


def png_bytes(color='red'):
    from PIL import Image
    stream = BytesIO()
    Image.new('RGB', (3, 3), color).save(stream, format='PNG')
    return stream.getvalue()


def test_profile_rejects_html_even_with_image_filename(auth_app, sql_state, monkeypatch):
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    response = client.post('/cliente/registro', data=registration(
        foto=(BytesIO(b'<script>alert(1)</script>'), 'portrait.png')))
    assert response.status_code == 400
    from pathlib import Path
    assert not list(Path(auth_app.static_folder).rglob('*.png'))


@pytest.fixture
def sql_state(auth_app, tmp_path, monkeypatch):
    """SQLite is only the ODBC boundary double; business services run unchanged."""
    from app.auth import routes
    from app.services import auth_challenges

    database = str(tmp_path / 'auth.sqlite')
    with sqlite3.connect(database) as conn:
        conn.executescript('''
            CREATE TABLE AuthChallenges (Token TEXT PRIMARY KEY, Kind TEXT, Subject TEXT,
                Verifier TEXT, Secret TEXT, Binding TEXT, ExpiresAt INTEGER,
                Attempts INTEGER, Verified INTEGER, Consumed INTEGER);
            CREATE TABLE Usuarios (ID INTEGER PRIMARY KEY, TOTPSecret TEXT, TOTPEnabled INTEGER, Activo INTEGER);
            INSERT INTO Usuarios VALUES (4, NULL, 0, 1);
            CREATE TABLE Clientes (ID INTEGER PRIMARY KEY, Nombre TEXT, Apellidos TEXT, Telefono TEXT,
                PasswordHash TEXT, Genero TEXT, FechaNacimiento TEXT, RutaFotoPerfil TEXT,
                EsInvitado INTEGER, NivelConfianzaID INTEGER);
        ''')

    class Cursor:
        def __init__(self, conn):
            self.cursor = conn.cursor()

        def execute(self, sql, *params):
            sql = sql.replace(' WITH (UPDLOCK, HOLDLOCK)', '')
            self.cursor.execute(sql, params)
            return self

        def fetchone(self):
            return self.cursor.fetchone()

    class Connection:
        def __init__(self):
            self.conn = sqlite3.connect(database)

        def cursor(self):
            return Cursor(self.conn)

        def commit(self):
            self.conn.commit()

        def rollback(self):
            self.conn.rollback()

        def close(self):
            self.conn.close()

    def query(sql, *params):
        with sqlite3.connect(database) as connection:
            return connection.execute(sql, params).fetchall()

    def get_user(uid):
        rows = query('SELECT TOTPSecret, TOTPEnabled FROM Usuarios WHERE ID = ? AND Activo = 1', int(uid))
        return User(int(uid), 'qa', 'QA', 1, 'SuperAdmin', rows[0][0], rows[0][1]) if rows else None

    def get_customer(phone):
        rows = query('SELECT ID, Nombre, Apellidos, PasswordHash FROM Clientes WHERE Telefono = ?', phone)
        return ((Cliente(rows[0][0], rows[0][1], rows[0][2], phone, False, 1), rows[0][3])
                if rows else (None, None))

    sent = []
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'test-sid')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'test-token')
    monkeypatch.setattr(routes, 'Client', lambda *args: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: sent.append(kwargs))))
    monkeypatch.setattr(routes, 'get_db_connection', Connection)
    monkeypatch.setattr(auth_challenges, 'get_db_connection', Connection)
    monkeypatch.setattr(routes.User, 'get_by_id', get_user)
    monkeypatch.setattr(routes.Cliente, 'get_by_telefono', get_customer)
    auth_app.login_manager._user_callback = lambda identity: (
        get_user(identity.split('_')[1]) if identity.startswith('emp_') else None)
    return SimpleNamespace(query=query, sent=sent, connect=Connection, get_user=get_user)


def verify_phone(client, sql_state, phone='+50588887777'):
    response = client.post('/api/enviar_codigo_sms', json={'telefono': phone})
    assert response.status_code == 200
    code = re.search(r'\d{6}$', sql_state.sent[-1]['body'])[0]
    assert client.post('/api/verificar_codigo_sms', json={'telefono': phone, 'codigo': code}).status_code == 200
    return code


def test_sms_opaque_cookie_and_hashed_database_verifier(auth_app, sql_state):
    client = auth_app.test_client()
    code = verify_phone(client, sql_state, '8888-7777')
    with client.session_transaction() as cookie:
        assert {key for key in cookie if not key.startswith('_')} == {'sms_challenge_id'}
        assert code not in str(dict(cookie))
    row = sql_state.query('SELECT Subject, Verifier, Secret, Verified FROM AuthChallenges')[0]
    assert row[0] == '+50588887777' and row[1] != code and row[2] == '' and row[3] == 1


def test_registration_requires_matching_verified_phone(auth_app, sql_state):
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    data = registration()
    data['telefono'] = '+50588886666'
    assert client.post('/cliente/registro', data=data).status_code == 400
    assert sql_state.query('SELECT COUNT(*) FROM Clientes')[0][0] == 0


def test_expired_verified_sms_cannot_register(auth_app, sql_state):
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    sql_state.query('UPDATE AuthChallenges SET ExpiresAt = 1')
    assert client.post('/cliente/registro', data=registration()).status_code == 400
    assert sql_state.query('SELECT COUNT(*) FROM Clientes')[0][0] == 0


def test_sms_five_wrong_attempts_lock_even_correct_code(auth_app, sql_state):
    client = auth_app.test_client()
    client.post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    code = re.search(r'\d{6}$', sql_state.sent[-1]['body'])[0]
    wrong = '000001' if code == '000000' else '000000'
    for _ in range(5):
        assert client.post('/api/verificar_codigo_sms', json={'telefono': '+50588887777', 'codigo': wrong}).status_code == 400
    assert client.post('/api/verificar_codigo_sms', json={'telefono': '+50588887777', 'codigo': code}).status_code == 400


def test_sms_resend_is_throttled_across_independent_sessions(auth_app,sql_state):
    first,second=auth_app.test_client(),auth_app.test_client()
    assert first.post('/api/enviar_codigo_sms',json={'telefono':'+50588887777'}).status_code==200
    cookie=first.get_cookie('session').value
    assert second.post('/api/enviar_codigo_sms',json={'telefono':'+50588887777'}).status_code==429
    assert len(sql_state.sent)==1
    first.set_cookie('session',cookie)
    code=re.search(r'\d{6}$',sql_state.sent[-1]['body'])[0]
    assert first.post('/api/verificar_codigo_sms',json={'telefono':'+50588887777','codigo':code}).status_code==200


def test_sms_fifth_correct_attempt_still_allows_registration(auth_app, sql_state):
    client = auth_app.test_client()
    client.post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    code = re.search(r'\d{6}$', sql_state.sent[-1]['body'])[0]
    wrong = '000001' if code == '000000' else '000000'
    for _ in range(4):
        client.post('/api/verificar_codigo_sms', json={'telefono': '+50588887777', 'codigo': wrong})
    assert client.post('/api/verificar_codigo_sms', json={'telefono': '+50588887777', 'codigo': code}).status_code == 200
    assert client.post('/cliente/registro', data=registration()).status_code == 302
    assert sql_state.query('SELECT COUNT(*) FROM Clientes')[0][0] == 1


def test_sms_grant_consumed_once_across_cloned_sessions(auth_app, sql_state):
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    clone = auth_app.test_client()
    clone.set_cookie('session', client.get_cookie('session').value)
    assert client.post('/cliente/registro', data=registration()).status_code == 302
    # Remove customer to make reusing an already consumed grant independently observable.
    sql_state.query('DELETE FROM Clientes')
    assert clone.post('/cliente/registro', data=registration()).status_code == 400
    assert sql_state.query('SELECT COUNT(*) FROM Clientes')[0][0] == 0


def test_resending_replaces_previous_sms_even_for_cookie_clone(auth_app, sql_state,monkeypatch):
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    clone = auth_app.test_client()
    clone.set_cookie('session', client.get_cookie('session').value)
    from app.services import auth_challenges
    later=auth_challenges.time.time()+61
    monkeypatch.setattr(auth_challenges.time,'time',lambda:later)
    client.post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    assert clone.post('/cliente/registro', data=registration()).status_code == 400


def test_profile_rewrites_pixels_discards_payload_and_uses_unique_names(auth_app, sql_state):
    from pathlib import Path
    from PIL import Image
    saved = []
    for phone, color in [('+50588887777', 'red'), ('+50588886666', 'blue')]:
        client = auth_app.test_client()
        verify_phone(client, sql_state, phone)
        data = registration(foto=(BytesIO(png_bytes(color) + b'<script>bad()</script>'), 'same.png'))
        data['telefono'] = phone
        assert client.post('/cliente/registro', data=data).status_code == 302
        path = sql_state.query('SELECT RutaFotoPerfil FROM Clientes WHERE Telefono = ?', phone)[0][0]
        saved.append(path)
        file = Path(auth_app.static_folder) / path
        assert b'<script>' not in file.read_bytes()
        with Image.open(file) as image:
            assert image.format == 'JPEG' and image.size == (3, 3)
        assert auth_app.test_client().get('/static/' + path).status_code == 200
    assert saved[0] != saved[1]


def begin_totp(client, monkeypatch, sql_state):
    from app.auth import routes
    monkeypatch.setattr(routes, 'totp_is_required', lambda: True)
    monkeypatch.setattr(routes.User, 'get_by_username', lambda _: (sql_state.get_user(4), generate_password_hash('password')))
    return client.post('/login', data={'identificador': 'qa', 'password': 'password'})


def test_totp_enrollment_confirms_before_login_and_survives_new_worker(auth_app, sql_state, monkeypatch):
    import pyotp
    client = auth_app.test_client()
    assert begin_totp(client, monkeypatch, sql_state).location.endswith('/login/totp/enroll')
    page = client.get('/login/totp/enroll')
    assert page.status_code == 200 and page.headers['Cache-Control'] == 'no-store'
    secret = sql_state.query('SELECT Secret FROM AuthChallenges')[0][0]
    assert secret.encode() in page.data
    with client.session_transaction() as cookie:
        assert '_user_id' not in cookie and secret not in str(dict(cookie))
    assert client.get('/perfil/setup_totp').status_code == 302
    worker = auth_app.test_client()
    worker.set_cookie('session', client.get_cookie('session').value)
    assert worker.post('/login/totp/enroll', data={'totp_code': pyotp.TOTP(secret).now()}).status_code == 302
    with worker.session_transaction() as cookie:
        assert cookie['_user_id'] == 'emp_4'
        assert 'totp_challenge_id' not in cookie
    assert sql_state.query('SELECT TOTPEnabled FROM Usuarios')[0][0] == 1


def test_expired_totp_enrollment_cannot_activate(auth_app, sql_state, monkeypatch):
    import pyotp
    client = auth_app.test_client()
    begin_totp(client, monkeypatch, sql_state)
    secret = sql_state.query('SELECT Secret FROM AuthChallenges')[0][0]
    sql_state.query('UPDATE AuthChallenges SET ExpiresAt = 1')
    response = client.post('/login/totp/enroll', data={'totp_code': pyotp.TOTP(secret).now()})
    assert response.location.endswith('/login')
    with client.session_transaction() as cookie:
        assert '_user_id' not in cookie
    assert sql_state.query('SELECT TOTPEnabled FROM Usuarios')[0][0] == 0


def test_totp_reset_invalidates_pending_login_and_allows_new_enrollment(auth_app, sql_state, monkeypatch):
    import pyotp
    old = pyotp.random_base32()
    sql_state.query('UPDATE Usuarios SET TOTPSecret = ?, TOTPEnabled = 1', old)
    client = auth_app.test_client()
    assert begin_totp(client, monkeypatch, sql_state).location.endswith('/login/totp')
    sql_state.query('UPDATE Usuarios SET TOTPSecret = NULL, TOTPEnabled = 0')
    response = client.post('/login/totp', data={'totp_code': pyotp.TOTP(old).now()})
    assert response.location.endswith('/login')
    with client.session_transaction() as cookie:
        assert '_user_id' not in cookie
    assert begin_totp(client, monkeypatch, sql_state).location.endswith('/login/totp/enroll')


def test_totp_enrollment_locks_after_five_wrong_attempts(auth_app, sql_state, monkeypatch):
    import pyotp
    client = auth_app.test_client()
    begin_totp(client, monkeypatch, sql_state)
    secret = sql_state.query('SELECT Secret FROM AuthChallenges')[0][0]
    wrong = '000001' if pyotp.TOTP(secret).now() == '000000' else '000000'
    for _ in range(5):
        client.post('/login/totp/enroll', data={'totp_code': wrong})
    response = client.post('/login/totp/enroll', data={'totp_code': pyotp.TOTP(secret).now()})
    assert response.location.endswith('/login')
    assert sql_state.query('SELECT TOTPEnabled FROM Usuarios')[0][0] == 0


def test_customer_login_accepts_same_local_format_as_registration(auth_app, sql_state, monkeypatch):
    from app.auth import routes
    client = auth_app.test_client()
    verify_phone(client, sql_state, '8888-7777')
    assert client.post('/cliente/registro', data=registration()).status_code == 302
    monkeypatch.setattr(routes.User, 'get_by_username', lambda _: (None, None))
    other = auth_app.test_client()
    response = other.post('/login', data={'identificador': '8888-7777', 'password': 'a-good-test-password'})
    assert response.status_code == 302
    assert response.location.endswith('/pos')
    with other.session_transaction() as cookie:
        assert cookie['_user_id'].startswith('cli_')


def test_failed_customer_insert_rolls_back_sms_consumption_and_image(auth_app, sql_state):
    from pathlib import Path
    client = auth_app.test_client()
    verify_phone(client, sql_state)
    sql_state.query("CREATE TRIGGER reject_customer BEFORE INSERT ON Clientes BEGIN SELECT RAISE(ABORT, 'forced'); END")
    response = client.post('/cliente/registro', data=registration(foto=(BytesIO(png_bytes()), 'photo.png')))
    assert response.status_code == 503
    assert sql_state.query('SELECT Consumed FROM AuthChallenges')[0][0] == 0
    assert not list(Path(auth_app.static_folder).rglob('*.jpg'))
    sql_state.query('DROP TRIGGER reject_customer')
    assert client.post('/cliente/registro', data=registration()).status_code == 302


def test_no_totp_policy_database_connection_cannot_skip_second_factor(auth_app, monkeypatch):
    from app.auth import routes
    def unavailable():
        raise RuntimeError('database unavailable')
    monkeypatch.setattr(routes, 'get_db_connection', unavailable)
    with auth_app.app_context():
        assert routes.totp_is_required() is True


@pytest.mark.parametrize('path', ['/login/totp', '/login/totp/enroll'])
def test_totp_without_partial_session_redirects_without_database_access(auth_app, path):
    response = auth_app.test_client().get(path)
    assert response.status_code == 302 and response.location.endswith('/login')


def test_totp_existing_authenticator_login_consumes_partial_grant(auth_app, sql_state, monkeypatch):
    import pyotp
    secret = pyotp.random_base32()
    sql_state.query('UPDATE Usuarios SET TOTPSecret = ?, TOTPEnabled = 1', secret)
    client = auth_app.test_client()
    assert begin_totp(client, monkeypatch, sql_state).location.endswith('/login/totp')
    clone = auth_app.test_client()
    clone.set_cookie('session', client.get_cookie('session').value)
    assert client.post('/login/totp', data={'totp_code': pyotp.TOTP(secret).now()}).status_code == 302
    with client.session_transaction() as cookie:
        assert cookie['_user_id'] == 'emp_4'
    assert clone.post('/login/totp', data={'totp_code': pyotp.TOTP(secret).now()}).location.endswith('/login')
    with clone.session_transaction() as cookie:
        assert '_user_id' not in cookie


def test_existing_local_customer_phone_prevents_duplicate_registration(auth_app, sql_state):
    sql_state.query("INSERT INTO Clientes (Nombre, Apellidos, Telefono) VALUES ('Existing', 'Customer', '88887777')")
    response = auth_app.test_client().post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    assert response.status_code == 400


def test_sms_send_response_never_contains_code_with_configured_provider(auth_app, sql_state):
    client = auth_app.test_client()
    response = client.post('/api/enviar_codigo_sms', json={'telefono': '+50588887777'})
    code = re.search(r'\d{6}$', sql_state.sent[-1]['body'])[0]
    assert response.status_code == 200
    assert code.encode() not in response.data
    assert 'dev_codigo' not in response.json
