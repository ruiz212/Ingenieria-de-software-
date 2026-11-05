from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


def test_tools_do_not_accept_identity_from_model():
    from app.whatsapp.tools import Tools
    tools = Tools(None, {'id': 1, 'token': 'private', 'phone': '+50588888888'})
    with pytest.raises(ValueError, match='argumentos'):
        tools.call('consultar_mis_cotizaciones', {'telefono': '+50577777777'}, 'op')


def test_delivery_policy_requires_full_notice():
    from app.whatsapp.policies import delivery_date
    now = datetime(2026, 11, 4, 15)
    with pytest.raises(ValueError):
        delivery_date('2026-11-05T10:00', 24, now)
    assert delivery_date('2026-11-05T16:00', 24, now) == now + timedelta(hours=25)


def test_reference_image_checks_actual_content(tmp_path):
    from app.whatsapp.media import save_image
    with pytest.raises(ValueError):
        save_image(b'not a jpeg', tmp_path)
    assert not list(tmp_path.iterdir())


def test_reference_image_reencodes_and_limits_size(tmp_path):
    from io import BytesIO
    from PIL import Image
    from app.whatsapp.media import save_image
    image = BytesIO()
    Image.new('RGB', (8, 8)).save(image, 'PNG')
    name = save_image(image.getvalue(), tmp_path)
    assert name.endswith('.jpg') and (tmp_path / name).is_file()
    with pytest.raises(ValueError):
        save_image(b'x' * (5 * 1024 * 1024 + 1), tmp_path)


def test_agent_bounds_tool_loop_and_injects_no_model_identity():
    from app.whatsapp.agent import Agent
    class Model:
        def complete(self, messages, schemas):
            return {'calls': [{'name': 'consultar_catalogo', 'args': {}}]}
    class Tools:
        schemas = []
        calls = 0
        def call(self, name, args, key):
            self.calls += 1
            return []
    tools = Tools()
    text = Agent(Model()).reply('hola', [], tools, 'message-1')
    assert tools.calls == 4
    assert 'persona' in text


def test_agent_uses_tool_results_and_reports_errors():
    from app.whatsapp.agent import Agent
    class Model:
        calls = 0
        def complete(self, messages, schemas):
            self.calls += 1
            if self.calls == 1:
                return {'calls': [{'name': 'inventar_precio', 'args': {}}]}
            assert 'error' in str(messages[-1])
            return {'text': 'Debo solicitar una cotización.'}
    class Tools:
        schemas = []
        def call(self, name, args, key):
            raise ValueError('Herramienta no autorizada')
    assert Agent(Model()).reply('precio', [], Tools(), 'm') == 'Debo solicitar una cotización.'


def test_transport_rejects_groups_and_opaque_lid():
    from app.whatsapp.client import sender_phone
    assert sender_phone('50588888888@s.whatsapp.net') == '+50588888888'
    for jid in ('123@g.us', '123@lid', 'status@broadcast'):
        with pytest.raises(ValueError):
            sender_phone(jid)


def test_mutating_tools_require_explicit_confirmation():
    from app.whatsapp.tools import Tools
    tools = Tools(None, {'id': 1, 'token': 'private', 'phone': '+50588888888'})
    with pytest.raises(ValueError, match='confirmación'):
        tools.call('responder_cotizacion', {'cotizacion_id': 42, 'decision': 'aceptar'}, 'op')


@pytest.mark.parametrize('mode', ['HUMANO', 'IA'])
def test_worker_does_not_invoke_model_in_human_mode(mode):
    from app.whatsapp.worker import process
    class Store:
        def command(self, item): return False, None
        def history(self, sid): return []
        def finish(self, item, response): self.response = response
    class Agent:
        calls = 0
        def reply(self, *args):
            self.calls += 1
            return 'respuesta'
    store, agent = Store(), Agent()
    process(store, agent, {'Modo': mode, 'Texto': 'hola', 'id': 1, 'ID': 5})
    assert agent.calls == (1 if mode == 'IA' else 0)
    assert store.response == ('respuesta' if mode == 'IA' else None)


def test_human_mode_cannot_confirm_a_mutation():
    from app.whatsapp.worker import process
    class Store:
        def command(self, item): raise AssertionError('Human mode cannot execute commands')
        def finish(self, item, response): assert response is None
    process(Store(), None, {'Modo': 'HUMANO', 'Texto': 'CONFIRMAR'})


@pytest.mark.parametrize('role,allowed', [('Admin', True), ('Cliente', False), ('Estandar', False), ('SuperAdmin', True)])
def test_panel_access_is_limited_to_management(monkeypatch, role, allowed):
    from flask import Flask
    from flask_login import LoginManager
    from app.models import User
    from app.admin import admin_bp
    from app.whatsapp import routes
    app = Flask(__name__)
    app.secret_key = 'synthetic-only'
    login = LoginManager(app)
    login.user_loader(lambda uid: User(7, 'synthetic', 'Test', 1, role))
    app.register_blueprint(admin_bp)
    monkeypatch.setattr(routes, 'snapshot', lambda sid=None: ({'Activo': False, 'Estado': 'Desconectado'}, [], []))
    monkeypatch.setattr('app.security.notify_security_403', lambda *a, **k: None)
    # Avoid other product template globals in this access-control test.
    monkeypatch.setattr(routes, 'render_template', lambda *a, **k: 'panel')
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_7'
    response = client.get('/admin/whatsapp', headers={'Accept': 'application/json'})
    assert response.status_code == (200 if allowed else 403)
