"""Quotation reference boundary tests; isolated storage and no SQL/SMTP network."""
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import create_app
from app.models import Cliente
from app.pos import routes


@pytest.fixture
def web_case(tmp_path, monkeypatch):
    import smtplib
    def block_smtp(*args, **kwargs):
        raise AssertionError('Real SMTP is forbidden in reference tests')
    monkeypatch.setattr(smtplib, 'SMTP', block_smtp)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', block_smtp)
    class Config:
        TESTING = True
        SECRET_KEY = 'isolated-reference-regression'
        WTF_CSRF_ENABLED = False

    app = create_app(Config)
    app.static_folder = str(tmp_path / 'static')
    actor = Cliente(666, 'Synthetic', 'Customer', '88888888', True, 1)
    monkeypatch.setattr(app.login_manager, '_user_callback', lambda _: actor)
    monkeypatch.delenv('IMGBB_API_KEY', raising=False)
    stored = []
    cursor = SimpleNamespace(fetchone=lambda: (91,))
    conn = SimpleNamespace(cursor=lambda: cursor, commit=lambda: None,
                           rollback=lambda: None, close=lambda: None)
    monkeypatch.setattr(routes, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(routes, 'execute_sp', lambda cur, name, params, **kw: stored.append(params))
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = actor.get_id()
        session['_fresh'] = True
    return app, client, stored


def quote(client, image):
    return client.post('/api/cotizaciones', json={
        'especificaciones': 'Synthetic design', 'fecha_entrega': '2026-12-01',
        'ruta_imagen_referencia': image,
    })


@pytest.mark.parametrize('image', [
    'x"><img src="data:image/png;base64,invalid" onerror="window.__quoteXSS=true">',
    'javascript:alert(1)', 'data:image/svg+xml,<svg onload=alert(1)>',
    '//i.ibb.co/id/photo.png', 'http://i.ibb.co/id/photo.png',
    'https://evil.example/photo.png', 'https://i.ibb.co.evil.example/id/photo.png',
    'https://i.ibb.co@evil.example/id/photo.png',
    'https://user:pass@i.ibb.co/id/photo.png', 'https://i.ibb.co:444/id/photo.png',
    'https://i.ibb.co/id/photo.png?redirect=https://evil.example',
    'https://i.ibb.co/id/photo.svg', 'https://i.ibb.co/id/photo.png#fragment',
    'https://i.ibb.co/id/%22photo.png', 'https://i.ibb.co/id/../photo.png',
    'https://i.ibb.co/id/pho\nto.png', ' https://i.ibb.co/id/photo.png',
    'uploads/referencias/../../private.png', 'uploads/referencias/missing.png',
    'uploads/productos/not-a-reference.png', '/static/uploads/referencias/%2e%2e/private.png',
    ['uploads/referencias/photo.png'], 42,
])
def test_quote_rejects_untrusted_reference_before_persistence(web_case, image):
    _, client, stored = web_case
    response = quote(client, image)
    assert response.status_code == 400
    assert stored == []


@pytest.mark.parametrize('image', [None, '', 'https://i.ibb.co/aB12cdEF/photo-1.png'])
def test_quote_keeps_supported_optional_and_imgbb_references(web_case, image):
    _, client, stored = web_case
    assert quote(client, image).status_code == 200
    assert stored[0][4] == (image or None)


def test_uploaded_reference_is_accepted_in_store_and_pos_path_forms(web_case):
    _, client, stored = web_case
    response = client.post('/api/upload_referencia', data={
        'foto': (BytesIO(b'synthetic image'), 'design.png'),
    })
    assert response.status_code == 200
    path = response.json['ruta']
    for reference in [path, '/static/' + path, 'static/' + path]:
        assert quote(client, reference).status_code == 200
        assert stored[-1][4] == path


@pytest.mark.parametrize('image, expected', [
    ('https://i.ibb.co/Ab12Cd/design.webp', 200),
    ('https://evil.example/design.png', 500),
])
def test_imgbb_upload_only_returns_an_approved_image_origin(web_case, monkeypatch, image, expected):
    import requests
    _, client, _ = web_case
    monkeypatch.setenv('IMGBB_API_KEY', 'synthetic-key')
    monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: SimpleNamespace(
        json=lambda: {'success': True, 'data': {'url': image}}))
    response = client.post('/api/upload_referencia', data={
        'foto': (BytesIO(b'synthetic image'), 'design.png'),
    })
    assert response.status_code == expected
    if expected == 200:
        assert response.json['ruta'] == image
    else:
        assert 'ruta' not in response.json
