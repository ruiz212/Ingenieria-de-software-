"""Role-aware home navigation, exercising the hub and real permission decorator.

Destination bodies are replaced with SQL-free sentinels; their role lists come
from the actual route decorators, so changes in access policy cannot go unnoticed.
"""
import ast
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, render_template
from flask_login import LoginManager

from app.auth.decorators import roles_required
from app.hub import hub_bp

ROOT = Path(__file__).resolve().parents[1]
DESTINATIONS = {
    '/admin/dashboard': ('admin.dashboard', 'app/admin/routes_dashboard.py', 'dashboard'),
    '/pos': ('pos.index', 'app/pos/routes.py', 'index'),
    '/monitor': ('monitor.monitor_pedidos', 'app/monitor/routes.py', 'monitor_pedidos'),
}


def permitted_roles(source, function):
    tree = ast.parse((ROOT / source).read_text(encoding='utf-8-sig'))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    guard = next(item for item in node.decorator_list
                 if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
                 and item.func.id == 'roles_required')
    return tuple(ast.literal_eval(arg) for arg in guard.args)


class BrandLink(HTMLParser):
    href = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'dock-brand' in attrs.get('class', '').split():
            self.href = attrs['href']


@pytest.mark.parametrize(('role', 'destination'), [
    ('SuperAdmin', '/admin/dashboard'), ('Admin', '/admin/dashboard'),
    ('Estandar', '/pos'), ('Operativo', '/monitor'),
    ('Cliente', '/pos'), ('Invitado', '/pos'),
])
def test_brand_reaches_the_roles_authorized_home_without_denied_access(role, destination):
    user = SimpleNamespace(is_authenticated=True, is_active=True, is_anonymous=False,
                           id=99, rol_nombre=role, nombre_completo='Cuenta QA')
    app = Flask(__name__, template_folder=str(ROOT / 'templates'))
    app.config.update(TESTING=True, SECRET_KEY='navigation-fixture-only')
    login = LoginManager(app)
    login.request_loader(lambda request: user)
    app.register_blueprint(hub_bp)
    app.add_url_rule('/admin/dgi', endpoint='admin.dgi_dashboard', view_func=lambda: '')
    for route, (endpoint, source, function) in DESTINATIONS.items():
        app.add_url_rule(route, endpoint=endpoint,
                         view_func=roles_required(*permitted_roles(source, function))(lambda: 'authorized-home'))
    with app.test_request_context('/monitor'):
        parser = BrandLink()
        parser.feed(render_template('admin/sidebar.html', current_user=user))
    assert parser.href is not None
    client = app.test_client()
    response = client.get(parser.href)
    if parser.href == '/':
        assert response.status_code == 302
        assert response.location == destination
        response = client.get(response.location)
    else:
        assert parser.href == destination
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'authorized-home'
    with client.session_transaction() as session:
        assert not session.get('_flashes'), 'The brand must not trigger an access-denied detour'
