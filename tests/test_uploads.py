"""Regression checks for images used by catalog, CRM and quotations."""
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import create_app
from app.models import User


@pytest.fixture
def app(tmp_path, monkeypatch):
    class TestConfig:
        TESTING = True
        SECRET_KEY = 'isolated-upload-regression'
        WTF_CSRF_ENABLED = False
        MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    monkeypatch.delenv('IMGBB_API_KEY', raising=False)
    application = create_app(TestConfig)
    application.static_folder = str(tmp_path / 'served-static')
    application.login_manager._user_callback = lambda _: User(
        1, 'qa', 'QA', 1, 'SuperAdmin'
    )
    return application


def authenticated_client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_1'
        session['_fresh'] = True
    return client


@pytest.mark.parametrize('endpoint,field,folder,response_key', [
    ('/api/upload_referencia', 'foto', 'referencias', 'ruta'),
    ('/admin/api/productos/upload_imagen', 'imagen', 'productos', 'url'),
])
def test_local_upload_is_retrievable(app, endpoint, field, folder, response_key):
    from pathlib import Path

    client = authenticated_client(app)
    payload = b'local-image-fixture'
    response = client.post(endpoint, data={field: (BytesIO(payload), 'foto.png')})
    assert response.status_code == 200
    url = response.json[response_key]
    if not url.startswith('/static/'):
        url = '/static/' + url
    saved = list((Path(app.static_folder) / 'uploads' / folder).glob('*.png'))
    assert len(saved) == 1 and saved[0].read_bytes() == payload
    download = client.get(url)
    assert download.status_code == 200 and download.data == payload


@pytest.mark.parametrize('endpoint,field', [
    ('/api/upload_referencia', 'foto'),
    ('/admin/api/productos/upload_imagen', 'imagen'),
])
def test_upload_rejects_unsupported_extension(app, endpoint, field):
    client = authenticated_client(app)
    response = client.post(endpoint, data={field: (BytesIO(b'bad'), 'script.exe')})
    assert response.status_code == 400


def test_profile_photo_uses_served_static_folder(app, monkeypatch):
    from pathlib import Path
    from app.auth import routes

    class Cursor:
        def execute(self, *args):
            return self

    connection = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: None, close=lambda: None)
    monkeypatch.setattr(routes, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(routes.Cliente, 'get_by_telefono', lambda _: (None, None))
    client = app.test_client()
    import time
    with client.session_transaction() as session:
        session['sms_phone'] = '55550000'
        session['telefono_verificado'] = True
        session['sms_expires_at'] = time.time() + 600
    response = client.post('/cliente/registro', data={
        'nombre': 'QA', 'apellidos': 'Cliente', 'telefono': '55550000',
        'password': 'only-test-password', 'foto': (BytesIO(b'profile-fixture'), 'perfil.png'),
    })
    assert response.status_code == 302
    path = Path(app.static_folder) / 'uploads' / 'perfiles' / 'perfil.png'
    assert path.read_bytes() == b'profile-fixture'
    assert client.get('/static/uploads/perfiles/perfil.png').data == b'profile-fixture'
