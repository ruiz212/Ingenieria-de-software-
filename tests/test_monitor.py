import pytest
from app import create_app
from app.db import get_db_connection


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_monitor_access_unauthenticated(client):
    """Acceso no autenticado debe redirigir a /login."""
    res = client.get('/monitor')
    assert res.status_code == 302
    assert '/login' in res.headers.get('Location', '')


def test_monitor_access_admin(client):
    """Acceso con rol Admin debe responder 200 y cargar la vista."""
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'  # Amada (Admin)
        sess['_fresh'] = True

    res = client.get('/monitor')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'Monitor de Cocina' in html
    assert 'col-Pendiente' in html
    assert 'col-En_Proceso' in html
    assert 'col-Listo' in html


def test_monitor_access_operativo(client):
    """Acceso con rol Operativo (panadero) debe responder 200."""
    with client.session_transaction() as sess:
        sess['_user_id'] = '7'  # panadero (Operativo)
        sess['_fresh'] = True

    res = client.get('/monitor')
    assert res.status_code == 200


def test_monitor_api_pedidos_json(client):
    """Endpoint JSON de pedidos para el monitor."""
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True

    res = client.get('/api/monitor/pedidos')
    assert res.status_code == 200
    data = res.get_json()
    assert 'encargos' in data
    assert isinstance(data['encargos'], list)


def test_monitor_actualizar_estado(client):
    """Actualización y reversión fluida del estado de un pedido."""
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True

    # Obtener el primer encargo activo o usar uno de prueba
    res_pedidos = client.get('/api/monitor/pedidos')
    data = res_pedidos.get_json()
    encargos = data.get('encargos', [])

    if encargos:
        codigo = encargos[0]['codigo_seguimiento']

        # Cambiar a En Proceso
        res_proceso = client.put(f'/api/seguimiento/{codigo}/estado', json={'estado': 'En Proceso'})
        assert res_proceso.status_code == 200
        assert res_proceso.get_json()['nuevo_estado'] == 'En Proceso'

        # Cambiar a Listo
        res_listo = client.put(f'/api/seguimiento/{codigo}/estado', json={'estado': 'Listo'})
        assert res_listo.status_code == 200
        assert res_listo.get_json()['nuevo_estado'] == 'Listo'

        # Revertir a Pendiente (posibilidad de corrección en cocina)
        res_revert = client.put(f'/api/seguimiento/{codigo}/estado', json={'estado': 'Pendiente'})
        assert res_revert.status_code == 200
        assert res_revert.get_json()['nuevo_estado'] == 'Pendiente'


def test_seguimiento_publico(client):
    """Página de seguimiento público accesible sin sesión."""
    res = client.get('/seguimiento/CODIGO_INEXISTENTE')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'no corresponde a ninguna factura' in html or 'Encargo no encontrado' in html
