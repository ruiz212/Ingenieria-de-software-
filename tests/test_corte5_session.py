"""La actividad automática no debe prolongar una sesión de administración."""
from datetime import datetime, timezone

from app import create_app
from app.models import User
from flask_login.utils import encode_cookie
from flask_login import login_user


def _app():
    class Config:
        TESTING = True
        SECRET_KEY = 'corte5-session-test'
        WTF_CSRF_ENABLED = False
        PERMANENT_SESSION_LIFETIME = 600
        SESSION_REFRESH_EACH_REQUEST = False
        SQL_SERVER_CONNECTION_STRING = ''

    app = create_app(Config)
    app.login_manager._user_callback = lambda _: User(1, 'qa', 'QA', 1, 'SuperAdmin')
    return app


def _session(client, seconds_ago=0):
    with client.session_transaction() as value:
        value['_user_id'] = 'emp_1'
        value['_fresh'] = True
        value['last_user_action_at'] = int(datetime.now(timezone.utc).timestamp()) - seconds_ago
        value.permanent = True


def test_ping_renews_only_on_explicit_authenticated_post():
    client = _app().test_client()
    _session(client, seconds_ago=300)
    with client.session_transaction() as value:
        previous = value['last_user_action_at']
    status = client.get('/auth/ping')
    assert status.status_code == 200
    with client.session_transaction() as value:
        assert value['last_user_action_at'] == previous
    renewed = client.post('/auth/ping')
    assert renewed.status_code == 200
    assert renewed.json['expires_in_seconds'] == 600
    with client.session_transaction() as value:
        assert value['last_user_action_at'] > previous


def test_expired_session_rejects_ping_and_clears_identity():
    client = _app().test_client()
    _session(client, seconds_ago=601)
    result = client.post('/auth/ping')
    assert result.status_code == 401
    with client.session_transaction() as value:
        assert '_user_id' not in value


def test_anonymous_ping_does_not_create_session():
    client = _app().test_client()
    response = client.post('/auth/ping')
    assert response.status_code == 401
    with client.session_transaction() as value:
        assert 'last_user_action_at' not in value


def test_legacy_remember_cookie_cannot_bypass_idle_session():
    app = _app()
    client = app.test_client()
    client.set_cookie('remember_token', encode_cookie('emp_1', key=app.secret_key))
    response = client.get('/auth/ping')
    assert response.status_code == 401
    with client.session_transaction() as value:
        assert '_user_id' not in value


def test_real_login_starts_idle_clock():
    app = _app()
    app.add_url_rule('/qa-login', view_func=lambda: ('ok' if login_user(User(1, 'qa', 'QA', 1, 'SuperAdmin')) else 'error'))
    client = app.test_client()
    assert client.get('/qa-login').status_code == 200
    with client.session_transaction() as value:
        assert value['_user_id']
        assert value['last_user_action_at'] > 0
        assert value.permanent
