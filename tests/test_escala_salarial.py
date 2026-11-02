from types import SimpleNamespace
import pytest
from app import create_app
from app.models import EscalaSalarial, User


TABLA_EXCEL = {
    'sin puesto': SimpleNamespace(id=1, nivel='I', cargo='Sin Puesto', limite_inferior=100, limite_superior=140, salario_base=6519.58),
    'limpieza': SimpleNamespace(id=2, nivel='II', cargo='Limpieza', limite_inferior=141, limite_superior=180, salario_base=8572.96),
    'panadero aprendiz': SimpleNamespace(id=3, nivel='III', cargo='Panadero Aprendiz', limite_inferior=181, limite_superior=220, salario_base=10626.34),
    'cajero/dependienta': SimpleNamespace(id=4, nivel='IV', cargo='Cajero/Dependienta', limite_inferior=221, limite_superior=260, salario_base=12679.72),
    'cajero': SimpleNamespace(id=4, nivel='IV', cargo='Cajero', limite_inferior=221, limite_superior=260, salario_base=12679.72),
    'cocinero': SimpleNamespace(id=5, nivel='V', cargo='Cocinero', limite_inferior=261, limite_superior=300, salario_base=14733.10),
    'cocina': SimpleNamespace(id=5, nivel='V', cargo='Cocina', limite_inferior=261, limite_superior=300, salario_base=14733.10),
    'jefe de inventario/panadero junior': SimpleNamespace(id=6, nivel='VI', cargo='Jefe De Inventario/Panadero Junior', limite_inferior=301, limite_superior=340, salario_base=16786.48),
    'panadero junior': SimpleNamespace(id=6, nivel='VI', cargo='Panadero Junior', limite_inferior=301, limite_superior=340, salario_base=16786.48),
    'jefe de inventario': SimpleNamespace(id=6, nivel='VI', cargo='Jefe de Inventario', limite_inferior=301, limite_superior=340, salario_base=16786.48),
    'contador': SimpleNamespace(id=7, nivel='VII', cargo='Contador', limite_inferior=341, limite_superior=380, salario_base=18839.86),
    'panadero senior': SimpleNamespace(id=8, nivel='VIII', cargo='Panadero Senior', limite_inferior=381, limite_superior=420, salario_base=20893.24),
    'maestro panadero': SimpleNamespace(id=9, nivel='IX', cargo='Maestro Panadero', limite_inferior=421, limite_superior=460, salario_base=22946.62),
    'gerente general': SimpleNamespace(id=10, nivel='X', cargo='Gerente General', limite_inferior=461, limite_superior=500, salario_base=25000.00),
    'gerente': SimpleNamespace(id=10, nivel='X', cargo='Gerente', limite_inferior=461, limite_superior=500, salario_base=25000.00),
}


class MockCursor:
    def __init__(self):
        self.last_query = ''
        self.last_param = None

    def execute(self, sql, *params):
        self.last_query = sql
        self.last_param = params[0] if params else None
        return self

    def fetchone(self):
        if not self.last_param:
            return None
        query_key = str(self.last_param).strip().lower()
        if query_key in TABLA_EXCEL:
            return TABLA_EXCEL[query_key]
        for k, v in TABLA_EXCEL.items():
            if k in query_key or query_key in k:
                return v
        return None

    def fetchall(self):
        return list(TABLA_EXCEL.values())

    def close(self):
        pass


class MockConnection:
    def cursor(self):
        return MockCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def app():
    class TestConfig:
        TESTING = True
        SECRET_KEY = 'test-escala-salarial-secret'
        WTF_CSRF_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''
        SERVER_NAME = 'localhost'

    app = create_app(TestConfig)
    app.login_manager._user_callback = lambda _: User(1, 'admin_qa', 'Admin QA', 1, 'Admin')
    return app


@pytest.fixture
def client(app):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = 'emp_1'
        sess['_fresh'] = True
    return c


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Intervención de conexión para pruebas unitarias deterministas."""
    import app.models
    import app.db
    import app.admin.routes_hr
    mock_conn = MockConnection()
    monkeypatch.setattr(app.models, 'get_db_connection', lambda *args, **kwargs: mock_conn)
    monkeypatch.setattr(app.db, 'get_db_connection', lambda *args, **kwargs: mock_conn)
    monkeypatch.setattr(app.admin.routes_hr, 'get_db_connection', lambda *args, **kwargs: mock_conn)


def test_requisito_1_modelo_escala_salarial(app):
    """Valida el modelo EscalaSalarial y los campos exactos requeridos con los nuevos valores."""
    cargos_a_probar = {
        'Sin Puesto': ('I', 6519.58),
        'Limpieza': ('II', 8572.96),
        'Panadero Aprendiz': ('III', 10626.34),
        'Cajero': ('IV', 12679.72),
        'Cocinero': ('V', 14733.10),
        'Panadero Junior': ('VI', 16786.48),
        'Contador': ('VII', 18839.86),
        'Panadero Senior': ('VIII', 20893.24),
        'Maestro Panadero': ('IX', 22946.62),
        'Gerente General': ('X', 25000.00),
    }

    with app.app_context():
        for cargo_nombre, (nivel_esperado, salario_esperado) in cargos_a_probar.items():
            escala = EscalaSalarial.get_by_cargo(cargo_nombre)
            assert escala is not None, f"No se encontró escala para {cargo_nombre}"
            assert escala.nivel == nivel_esperado
            assert float(escala.salario_base) == salario_esperado
            
            d = escala.to_dict()
            assert 'id' in d
            assert 'nivel' in d
            assert 'cargo' in d
            assert 'limite_inferior' in d
            assert 'limite_superior' in d
            assert 'salario_base' in d


def test_requisito_2_api_escala_salarial_autocompletado(app, client):
    """Valida la consulta al backend para autocompletar el salario."""
    with app.test_request_context():
        # 1. Caso Cajero
        res = client.get('/admin/api/rrhh/escala-salarial?cargo=Cajero')
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'success'
        assert float(data['salario_base']) == 12679.72
        assert data['nivel'] == 'IV'

        # 2. Las 4 subcategorías de Panadero
        subcategorias = {
            'Panadero Aprendiz': 10626.34,
            'Panadero Junior': 16786.48,
            'Panadero Senior': 20893.24,
            'Maestro Panadero': 22946.62
        }
        for sub, sal in subcategorias.items():
            res = client.get(f'/admin/api/rrhh/escala-salarial?cargo={sub}')
            assert res.status_code == 200
            assert float(res.get_json()['salario_base']) == sal

        # 3. Path param
        res = client.get('/admin/api/rrhh/escala-salarial/Maestro%20Panadero')
        assert res.status_code == 200
        assert float(res.get_json()['salario_base']) == 22946.62

        # 4. Cargo inexistente
        res = client.get('/admin/api/rrhh/escala-salarial?cargo=InexistenteXYZ')
        assert res.status_code == 404

        # 5. Sin cargo
        res = client.get('/admin/api/rrhh/escala-salarial')
        assert res.status_code == 400


def test_requisito_2_y_3_frontend_template(app):
    """Valida que el template rrhh.html contenga el custom dropdown, submenú de panadero y salario readonly."""
    with app.test_request_context('/admin/rrhh'):
        from flask import render_template
        from datetime import datetime
        perfiles_mock = [
            {'cargo': 'Cajero'},
            {'cargo': 'Cocina'},
            {'cargo': 'Contador'},
            {'cargo': 'Gerente'},
            {'cargo': 'Ingeniero electronico'},
            {'cargo': 'Panadero'},
        ]
        html = render_template('admin/rrhh.html',
            user=User(1, 'admin', 'Admin', 1, 'Admin'),
            empleados=[], nominas=[], tasas={}, total_activos=0,
            monitor_hoy=[], datetime=datetime, perfiles=perfiles_mock,
            fecha_hoy='2026-10-24'
        )

        # Requisito 2: Salario Base en solo lectura (readonly) y id ne-salario
        assert 'id="ne-salario"' in html
        assert 'readonly' in html

        # Requisito 3: Custom Dropdown con cascada exclusivamente para Panadero con nuevos salarios
        assert 'id="cargo-dropdown-wrapper"' in html
        assert 'id="ne-cargo"' in html
        assert 'has-cascade' in html
        assert 'Panadero Aprendiz (Salario: C$ 10,626.34)' in html
        assert 'Panadero Junior (Salario: C$ 16,786.48)' in html
        assert 'Panadero Senior (Salario: C$ 20,893.24)' in html
        assert 'Maestro Panadero (Salario: C$ 22,946.62)' in html


def test_soft_delete_perfil_endpoint(client, app):
    """Valida el endpoint de soft delete y activación de perfiles de puesto."""
    with app.app_context():
        # Desactivar cargo
        res = client.post('/admin/api/rrhh/puestos/estado', json={'cargo': 'Ingeniero electronico', 'activo': False})
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'success'
        assert data['cargo'] == 'Ingeniero electronico'
        assert data['activo'] is False

        # Reactivar cargo
        res = client.post('/admin/api/rrhh/puestos/estado', json={'cargo': 'Ingeniero electronico', 'activo': True})
        assert res.status_code == 200
        assert res.get_json()['activo'] is True

        # Error sin cargo
        res = client.post('/admin/api/rrhh/puestos/estado', json={'cargo': ''})
        assert res.status_code == 400


def test_perfiles_render_con_estado_y_filtro_inactivos(app):
    """Valida que los puestos inactivos no aparezcan en el dropdown de nuevo empleado y tengan indicador visual."""
    with app.test_request_context('/admin/rrhh'):
        from flask import render_template
        from datetime import datetime
        perfiles_mock = [
            {'cargo': 'Cajero', 'perfil': 'Caja', 'obligaciones': 'Cobrar', 'competencias': 'POS', 'activo': True},
            {'cargo': 'Ingeniero electronico', 'perfil': 'Soporte', 'obligaciones': 'Redes', 'competencias': 'Hardware', 'activo': False},
            {'cargo': 'Panadero', 'perfil': 'Panadería', 'obligaciones': 'Hornear', 'competencias': 'Masas', 'activo': True},
        ]
        html = render_template('admin/rrhh.html',
            user=User(1, 'admin', 'Admin', 1, 'Admin'),
            empleados=[], nominas=[], tasas={}, total_activos=0,
            monitor_hoy=[], datetime=datetime, perfiles=perfiles_mock,
            fecha_hoy='2026-10-24'
        )

        # 1. Puesto inactivo tiene clase y badge correspondiente
        assert 'profile-card-inactive' in html
        assert 'status-inactivo' in html
        assert 'status-activo' in html

        # 2. Botón Editar perfil y botón toggle en footer de tarjeta
        assert 'btn-edit-profile' in html
        assert 'btn-toggle-status' in html
        assert 'rrhh-profile-card-footer' in html

        # 3. Puesto inactivo NO debe ser seleccionable en el dropdown de Nuevo Empleado
        dropdown_html = html[html.find('id="cargo-select-dropdown"'):html.find('id="ne-ingreso"')]
        assert 'data-value="Cajero"' in dropdown_html
        assert 'data-value="Ingeniero electronico"' not in dropdown_html
