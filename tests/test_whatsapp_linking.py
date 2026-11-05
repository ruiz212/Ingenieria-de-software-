"""Connection lifecycle tests never contact SQL Server or WhatsApp."""
from types import SimpleNamespace

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash


@pytest.mark.parametrize('password,otp,allowed', [('wrong', '123456', False), ('correct', 'bad', False), ('correct', '123456', True)])
def test_pairing_requires_current_password_and_enabled_second_factor(monkeypatch, password, otp, allowed):
    from app.whatsapp import security
    user = SimpleNamespace(id=7, username='synthetic', rol_nombre='Admin', totp_enabled=True, totp_secret='synthetic')
    monkeypatch.setattr(security.User, 'get_by_username', lambda name: (user, generate_password_hash('correct')))
    monkeypatch.setattr(security, 'reserve_attempt', lambda: True)
    attempts = []
    monkeypatch.setattr(security, 'record_auth_result', lambda success: attempts.append(success))
    monkeypatch.setattr(security.pyotp, 'TOTP', lambda secret: SimpleNamespace(verify=lambda code, **kw: code == '123456'))
    with Flask(__name__).test_request_context('/'):
        if allowed:
            security.verify_admin(user, password, otp)
        else:
            with pytest.raises(ValueError):
                security.verify_admin(user, password, otp)
    assert attempts[-1] is allowed


def test_pairing_checks_shared_lock_before_password(monkeypatch):
    from app.whatsapp import security
    monkeypatch.setattr(security, 'reserve_attempt', lambda: False)
    monkeypatch.setattr(security.User, 'get_by_username', lambda name: pytest.fail('Account locked'))
    with Flask(__name__).test_request_context('/'):
        with pytest.raises(ValueError, match='intentos'):
            security.verify_admin(SimpleNamespace(id=7), 'x', '')


class MemoryStore:
    def __init__(self): self.results = []
    def complete_link(self, *args): self.results.append(args)


def test_logout_failure_keeps_account_and_does_not_confirm_removal():
    from app.whatsapp.linking import apply_unlink
    store = MemoryStore()
    class Transport:
        status = 'Conectado'
        def logout(self): raise RuntimeError('network down')
        def stop(self): pytest.fail('Do not stop before revocation succeeds')
    assert apply_unlink(store, Transport(), {'SolicitudID': 'operation'}) is False
    assert store.results[0][0:2] == ('operation', False)


def test_unlink_revokes_remote_session_before_confirming_removal():
    from app.whatsapp.linking import apply_unlink
    events = []
    store = MemoryStore()
    transport = SimpleNamespace(status='Conectado', logout=lambda: events.append('logout'), stop=lambda: events.append('stop'))
    assert apply_unlink(store, transport, {'SolicitudID': 'operation'}) is True
    assert events == ['logout', 'stop']
    assert store.results[0][0:2] == ('operation', True)


def test_unlink_waits_for_reconnection_before_revoking_credentials():
    from app.whatsapp.linking import apply_unlink
    store = MemoryStore()
    transport = SimpleNamespace(status='Desconectado', logout=lambda: pytest.fail('Not connected'))
    assert apply_unlink(store, transport, {'SolicitudID': 'operation', 'Vinculado': True}) is None
    assert store.results == []


def test_pending_qr_cannot_prove_removal_of_a_previously_linked_account():
    from app.whatsapp.linking import apply_unlink
    store = MemoryStore()
    transport = SimpleNamespace(status='Esperando QR', stop=lambda: pytest.fail('Old remote account is unverified'))
    assert apply_unlink(store, transport, {'SolicitudID': 'operation', 'Vinculado': True}) is None
    assert store.results == []


def test_link_status_removes_qr_without_recent_reauthentication():
    from app.whatsapp.linking import public_state
    app = Flask(__name__)
    app.secret_key = 'synthetic'
    with app.test_request_context('/'):
        result = public_state({'QR': 'secret-qr', 'Estado': 'Esperando QR', 'ConnectionRevision': 2})
        assert result['QR'] is None
        assert result['needs_auth'] is True


def test_worker_can_initialize_without_gemini_credentials(monkeypatch):
    from app.whatsapp.worker import LazyAgent
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    agent = LazyAgent()
    assert agent.agent is None


@pytest.fixture
def panel(monkeypatch):
    from flask_login import LoginManager
    from app.models import User
    from app.admin import admin_bp
    from app.whatsapp import routes
    app = Flask(__name__)
    app.secret_key = 'synthetic'
    login = LoginManager(app)
    login.user_loader(lambda uid: User(7, 'admin', 'Synthetic', 1, 'Admin' if uid == 'emp_7' else 'Cliente'))
    app.register_blueprint(admin_bp)
    monkeypatch.setenv('WHATSAPP_ENABLED', '1')
    state = {'Activo': False, 'Estado': 'Esperando QR', 'QR': 'data:image/png;base64,synthetic',
             'ConnectionRevision': 3, 'Vinculado': False}
    monkeypatch.setattr(routes, 'snapshot', lambda sid=None, **kw: (state.copy(), [], []))
    monkeypatch.setattr('app.security.notify_security_403', lambda *a, **k: None)
    return app, state


def signed_client(app, uid='emp_7'):
    client = app.test_client()
    with client.session_transaction() as value:
        value['_user_id'] = uid
    return client


def test_status_does_not_leak_pairing_qr_before_identity_check(panel):
    app, state = panel
    response = signed_client(app).get('/admin/whatsapp/estado')
    assert response.status_code == 200
    assert response.json['QR'] is None
    assert response.headers['Cache-Control'] == 'no-store'


def test_link_form_reauthenticates_before_creating_request(panel, monkeypatch):
    from app.whatsapp import routes
    app, state = panel
    events = []
    def verify(*args):
        events.append('reauth')
        raise ValueError('Credenciales inválidas')
    monkeypatch.setattr(routes, 'verify_admin', verify)
    monkeypatch.setattr(routes.Store, 'request_link', lambda *a: pytest.fail('Reauthentication required'))
    response = signed_client(app).post('/admin/whatsapp', data={'action': 'link', 'revision': 3})
    assert response.status_code == 302
    assert events == ['reauth']


def test_successful_link_allows_temporary_qr_view_and_starts_local_process(panel, monkeypatch):
    from app.whatsapp import routes
    app, state = panel
    monkeypatch.setattr(routes, 'verify_admin', lambda *args: None)
    monkeypatch.setattr(routes.Store, 'request_link', lambda *args: state.copy())
    started = []
    monkeypatch.setattr(routes, 'start_local_worker', lambda: started.append(True) or True)
    client = signed_client(app)
    assert client.post('/admin/whatsapp', data={'action': 'link', 'revision': 3}).status_code == 302
    result = client.get('/admin/whatsapp/estado')
    assert result.json['QR'] == state['QR']
    assert started == [True]
    state['ConnectionRevision'] += 1
    assert client.get('/admin/whatsapp/estado').json['QR'] is None


def test_customer_cannot_view_company_connection_status(panel):
    app, state = panel
    response = signed_client(app, 'cli_8').get('/admin/whatsapp/estado', headers={'Accept': 'application/json'})
    assert response.status_code == 403


def test_unlink_requires_explicit_confirmation_and_does_not_reveal_qr(panel, monkeypatch):
    from app.whatsapp import routes
    app, state = panel
    monkeypatch.setattr(routes, 'verify_admin', lambda *a: pytest.fail('Confirm intent first'))
    monkeypatch.setattr(routes.Store, 'request_link', lambda *a: pytest.fail('Confirmation required'))
    client = signed_client(app)
    assert client.post('/admin/whatsapp', data={'action': 'unlink', 'revision': 3}).status_code == 302
    assert client.get('/admin/whatsapp/estado').json['QR'] is None


def test_pairing_post_cannot_bypass_application_csrf(panel, monkeypatch):
    from flask_wtf.csrf import CSRFProtect
    from app.whatsapp import routes
    app, _ = panel
    CSRFProtect(app)
    monkeypatch.setattr(routes, 'verify_admin', lambda *a: pytest.fail('Reject CSRF first'))
    assert signed_client(app).post('/admin/whatsapp', data={'action': 'link', 'password': 'synthetic'}).status_code == 400


def test_pairing_grant_expires_without_exposing_qr(monkeypatch):
    from flask import session
    from app.whatsapp.linking import public_state
    app = Flask(__name__)
    app.secret_key = 'synthetic'
    with app.test_request_context('/'):
        session['wa_pairing'] = {'until': 1, 'revision': 3}
        state = public_state({'ConnectionRevision': 3, 'QR': 'data:image/png;base64,private'})
        assert state['QR'] is None
        assert state['needs_auth'] is True


@pytest.mark.parametrize('debug,setting,allowed', [(False, None, False), (True, None, True), (True, '0', False), (False, '1', True)])
def test_process_launch_requires_local_debug_or_explicit_configuration(monkeypatch, tmp_path, debug, setting, allowed):
    from app.whatsapp import linking
    app = Flask(__name__)
    app.debug = debug
    app.instance_path = str(tmp_path)
    if setting is None:
        monkeypatch.delenv('WHATSAPP_MANAGED_WORKER', raising=False)
    else:
        monkeypatch.setenv('WHATSAPP_MANAGED_WORKER', setting)
    launches = []
    monkeypatch.setattr(linking.subprocess, 'Popen', lambda *a, **kw: launches.append((a, kw)))
    with app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
        assert linking.start_local_worker() is allowed
    assert bool(launches) is allowed
