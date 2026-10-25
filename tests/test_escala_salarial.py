from types import SimpleNamespace
import pytest
from app import create_app
from app.models import EscalaSalarial, User


TABLA_EXCEL = {
    'limpieza': SimpleNamespace(id=1, nivel='I', cargo='Limpieza', limite_inferior=None, limite_superior=100, salario_base=6519.58),
    'panadero aprendiz': SimpleNamespace(id=2, nivel='II', cargo='Panadero Aprendiz', limite_inferior=101, limite_superior=126, salario_base=8572.96),
    'cajero/depedienta': SimpleNamespace(id=3, nivel='III', cargo='Cajero/Depedienta', limite_inferior=127, limite_superior=159, salario_base=10626.34),
    'cajero': SimpleNamespace(id=4, nivel='III', cargo='Cajero', limite_inferior=127, limite_superior=159, salario_base=10626.34),
    'cocinero': SimpleNamespace(id=5, nivel='IV', cargo='Cocinero', limite_inferior=160, limite_superior=200, salario_base=12679.72),
    'cocina': SimpleNamespace(id=6, nivel='IV', cargo='Cocina', limite_inferior=160, limite_superior=200, salario_base=12679.72),
    'panadero junior': SimpleNamespace(id=7, nivel='V', cargo='Panadero Junior', limite_inferior=201, limite_superior=252, salario_base=14733.10),
    'jefe de inventario': SimpleNamespace(id=8, nivel='VI', cargo='Jefe de Inventario', limite_inferior=253, limite_superior=317, salario_base=16786.48),
    'panadero senior': SimpleNamespace(id=9, nivel='VII', cargo='Panadero Senior', limite_inferior=318, limite_superior=400, salario_base=18839.86),
    'contador': SimpleNamespace(id=10, nivel='VIII', cargo='Contador', limite_inferior=401, limite_superior=504, salario_base=20893.24),
    'maestro panadero': SimpleNamespace(id=11, nivel='IX', cargo='Maestro Panadero', limite_inferior=505, limite_superior=635, salario_base=22946.62),
    'gerente general': SimpleNamespace(id=12, nivel='X', cargo='Gerente General', limite_inferior=636, limite_superior=800, salario_base=25000.00),
    'gerente': SimpleNamespace(id=13, nivel='X', cargo='Gerente', limite_inferior=636, limite_superior=800, salario_base=25000.00),
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
    """Valida el modelo EscalaSalarial y los campos exactos requeridos."""
    cargos_a_probar = {
        'Limpieza': ('I', 6519.58),
        'Panadero Aprendiz': ('II', 8572.96),
        'Cajero': ('III', 10626.34),
        'Panadero Junior': ('V', 14733.10),
        'Panadero Senior': ('VII', 18839.86),
        'Maestro Panadero': ('IX', 22946.62),
        'Contador': ('VIII', 20893.24),
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
        assert float(data['salario_base']) == 10626.34
        assert data['nivel'] == 'III'

        # 2. Las 4 subcategorías de Panadero
        subcategorias = {
            'Panadero Aprendiz': 8572.96,
            'Panadero Junior': 14733.10,
            'Panadero Senior': 18839.86,
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

        # Requisito 3: Custom Dropdown con cascada exclusivamente para Panadero
        assert 'id="cargo-dropdown-wrapper"' in html
        assert 'id="ne-cargo"' in html
        assert 'has-cascade' in html
        assert 'Panadero Aprendiz' in html
        assert 'Panadero Junior' in html
        assert 'Panadero Senior' in html
        assert 'Maestro Panadero' in html


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
        # Buscamos las opciones dentro del dropdown de cargo
        dropdown_html = html[html.find('id="cargo-select-dropdown"'):html.find('id="ne-ingreso"')]
        assert 'data-value="Cajero"' in dropdown_html
        assert 'data-value="Ingeniero electronico"' not in dropdown_html

