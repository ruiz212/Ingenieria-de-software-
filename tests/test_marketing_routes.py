"""Integración de recomendaciones y panel sin tocar una base real."""

from datetime import datetime
from types import SimpleNamespace

from flask import Flask

from app import create_app
from app.models import User
from app.pos import routes as pos
from config import Config


class Connection:
    def __init__(self):
        self.closed = False
        self.commits = 0

    def cursor(self):
        return self

    def close(self):
        self.closed = True

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_public_store_passes_suggestions_to_page(monkeypatch):
    conn = Connection()
    product = dict(id=4, nombre='Bolillo', categoria='Pan', precio=15,
                   descuento=0, activo=True, es_ficticio=False, imagen_url='')
    monkeypatch.setattr(pos, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(pos, 'current_user', SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(pos, 'is_sqlserver_cursor', lambda cursor: False)
    monkeypatch.setattr(pos, '_cargar_datos_catalogo_publico',
                        lambda cursor: ([], [product], [], {}))
    monkeypatch.setattr(pos, 'store_recommendations',
                        lambda cursor, catalog, user, **kwargs: [{**product, 'motivo': 'Popular en la tienda'}],
                        raising=False)
    monkeypatch.setattr(pos, 'render_template', lambda name, **data: (name, data))

    name, data = pos.tienda_publica()

    assert name == 'tienda.html'
    assert data['recomendaciones'][0]['id'] == 4
    assert conn.closed


def test_registered_store_uses_personalized_suggestions(monkeypatch):
    conn = Connection()
    user = SimpleNamespace(is_authenticated=True, rol_nombre='Cliente', id=12, es_invitado=False)
    monkeypatch.setattr(pos, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(pos, 'current_user', user)
    monkeypatch.setattr(pos, '_cargar_datos_catalogo_publico', lambda cursor: ([], [], [], {}))
    monkeypatch.setattr(pos, 'store_recommendations',
                        lambda cursor, catalog, user, **kwargs: [{'id': 9, 'motivo': 'Uno de tus favoritos'}],
                        raising=False)
    monkeypatch.setattr(pos, 'render_template', lambda name, **data: (name, data))

    name, data = pos.index.__wrapped__.__wrapped__()

    assert name == 'tienda.html'
    assert data['recomendaciones'][0]['motivo'] == 'Uno de tus favoritos'
    assert conn.closed


def test_admin_marketing_trains_when_snapshot_is_missing(monkeypatch):
    from app.admin import routes_marketing as marketing

    conn = Connection()
    model = {'source_rows': 4, 'invoice_count': 2, 'products': {}, 'pairs': {},
             'trained_at': '2026-10-26T10:00:00'}
    monkeypatch.setattr(marketing, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(marketing, 'load_model', lambda cursor: None)
    monkeypatch.setattr(marketing, 'train_and_save', lambda cursor, now: model)
    monkeypatch.setattr(marketing, 'load_marketing_catalog', lambda cursor: [])
    monkeypatch.setattr(marketing, 'business_now', lambda: datetime(2026, 10, 26, 10))
    monkeypatch.setattr(marketing, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))
    monkeypatch.setattr(marketing, 'render_template', lambda name, **data: (name, data))

    name, data = marketing.mercadotecnia.__wrapped__.__wrapped__()

    assert name == 'admin/mercadotecnia.html'
    assert data['modelo']['source_rows'] == 4
    assert conn.commits == 1
    assert conn.closed


def test_cart_recommendations_accept_only_a_small_list_of_product_ids(monkeypatch):
    app = Flask(__name__)
    conn = Connection()
    monkeypatch.setattr(pos, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(pos, 'current_user', SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(pos, 'is_sqlserver_cursor', lambda cursor: False)
    monkeypatch.setattr(pos, 'load_marketing_catalog', lambda cursor: [dict(id=3, nombre='Café')], raising=False)
    monkeypatch.setattr(pos, 'store_recommendations',
                        lambda cursor, catalog, user, **kwargs: [dict(id=3, nombre='Café',
                            categoria='Bebidas', precio=35, descuento=0, motivo='Va bien junto')])
    with app.test_request_context('/api/mercadotecnia/recomendaciones?carrito=1,2'):
        response = pos.recomendaciones_tienda()
        assert response.get_json()['productos'][0]['id'] == 3
    assert conn.closed

    with app.test_request_context('/api/mercadotecnia/recomendaciones?carrito=1,2,3,4,5,6,7,8,9,10,11'):
        response, status = pos.recomendaciones_tienda()
        assert status == 400
        assert 'error' in response.get_json()


def test_real_store_template_renders_recommendations_without_database(monkeypatch):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'marketing-template-qa'
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)
    product = dict(id=4, nombre='Bolillo', categoria='Pan salado', precio=15,
                   descuento=0, activo=True, es_ficticio=False, imagen_url='', tasa_iva=0)
    monkeypatch.setattr(pos, 'get_db_connection', Connection)
    monkeypatch.setattr(pos, 'is_sqlserver_cursor', lambda cursor: False)
    monkeypatch.setattr(pos, '_cargar_datos_catalogo_publico',
                        lambda cursor: ([], [product], [], {}))
    monkeypatch.setattr(pos, 'store_recommendations',
                        lambda cursor, catalog, user, **kwargs: [{**product, 'motivo': 'Popular en la tienda'}])

    response = app.test_client().get('/tienda')

    assert response.status_code == 200
    assert 'Para acompañar tu pedido' in response.text
    assert 'Popular en la tienda' in response.text


def test_cashier_cannot_open_owner_marketing_panel(monkeypatch):
    import app.security as security

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'marketing-access-qa'
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)
    app.login_manager._user_callback = lambda _: User(5, 'cajero_qa', 'Cajero QA', 3, 'Estandar')
    monkeypatch.setattr(security, 'notify_security_403', lambda *args, **kwargs: None)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_5'
        session['_fresh'] = True

    response = client.get('/admin/mercadotecnia')

    assert response.status_code == 302
    assert '/admin/mercadotecnia' not in response.headers['Location']


def test_owner_panel_renders_trained_sales_and_actions(monkeypatch):
    from app.admin import routes_marketing as marketing

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'marketing-owner-qa'
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)
    app.login_manager._user_callback = lambda _: User(1, 'duena_qa', 'Dueña QA', 1, 'Admin')
    model = {
        'version': 1, 'trained_at': '2026-10-26T10:00:00', 'source_rows': 8,
        'sample_truncated': True,
        'invoice_count': 4, 'recent_invoices': 4, 'prior_invoices': 0,
        'revenue_30': 160.0, 'revenue_prior_30': 0.0,
        'products': {'4': {'score': 2, 'units_30': 8, 'units_prior_30': 0,
                           'revenue_30': 160.0, 'revenue_prior_30': 0.0}},
        'pairs': {}, 'daily': [{'day': '2026-10-26', 'revenue': 160.0}],
    }
    monkeypatch.setattr(marketing, 'get_db_connection', Connection)
    monkeypatch.setattr(marketing, 'load_model', lambda cursor: model)
    monkeypatch.setattr(marketing, 'load_marketing_catalog', lambda cursor: [
        dict(id=4, nombre='Bolillo', categoria='Pan salado', precio=20,
             descuento=10, activo=True, es_ficticio=False)])
    monkeypatch.setattr(marketing, 'business_now', lambda: datetime(2026, 10, 26, 11))
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_1'
        session['_fresh'] = True

    response = client.get('/admin/mercadotecnia')

    assert response.status_code == 200
    assert 'Lo que cuentan las ventas' in response.text
    assert 'Ventas en muestra' in response.text
    assert 'Bolillo' in response.text
    assert 'C$160.00' in response.text
