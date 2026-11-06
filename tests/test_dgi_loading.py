"""DGI reads must work with published procedures and restricted SQL roles."""
from datetime import date
from datetime import datetime
from contextlib import contextmanager
import json
import hashlib
from types import SimpleNamespace
import pyodbc
import pytest

from app.services import dgi_repository as repo


class RestrictedCursor:
    """Native boundary: deployed procedures work; tables are not selectable."""
    def execute(self, sql, *params):
        if sql.startswith('SELECT'):
            raise pyodbc.ProgrammingError('42000', 'SELECT permission denied (229)')
        deployed = {
            'EXEC fiscal.sp_ObtenerPeriodoDGIPorID':
                {'ID': 7, 'Desde': date(2026, 10, 1), 'Hasta': date(2026, 10, 31), 'Estado': 'Abierto'},
            'EXEC fiscal.sp_ObtenerRevisionDGIPorID':
                {'ID': 11, 'PeriodoID': 7, 'Estado': 'VALIDADO'},
        }
        key = sql.rsplit(' ?', 1)[0]
        if key not in deployed:
            raise pyodbc.ProgrammingError('42000', 'Could not find stored procedure (2812)')
        self.result = deployed[key]
        self.description = [(name,) for name in self.result]
        return self

    def fetchall(self):
        return [tuple(self.result.values())]


@pytest.mark.parametrize('read,identifier,expected', [
    (repo.get_period, 7, {'ID': 7, 'Desde': date(2026, 10, 1), 'Hasta': date(2026, 10, 31), 'Estado': 'Abierto'}),
    (repo.get_review, 11, {'ID': 11, 'PeriodoID': 7, 'Estado': 'VALIDADO'}),
])
def test_reads_work_without_direct_table_permissions(monkeypatch, read, identifier, expected):
    monkeypatch.setattr('app.db.is_sqlserver_cursor', lambda cursor: True)
    assert read(RestrictedCursor(), identifier) == expected


@pytest.fixture
def dgi_page(monkeypatch):
    from copy import deepcopy
    from app import create_app
    from app.models import User
    from app.admin import routes_dgi
    from app.services.dgi_engine import ENGINE_VERSION
    class Config:
        TESTING = True
        SECRET_KEY = 'dgi-loading-fixture'
        WTF_CSRF_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''
    app = create_app(Config)
    app.login_manager._user_callback = lambda _: User(1, 'synthetic', 'QA', 1, 'SuperAdmin')
    period = {'ID': 7, 'Desde': date(2026, 10, 1), 'Hasta': date(2026, 10, 31), 'Estado': 'Abierto'}
    review = {'ID': 11, 'PeriodoID': 7, 'Version': 1, 'Obligacion': 'Diagnóstico interno',
              'Motor': 'legacy', 'Huella': 'old', 'Estado': 'APROBADO',
              'ResultadoJSON': json.dumps({'estado': 'historico', 'valido': True}),
              'SnapshotJSON': '{}', 'CreadoEn': datetime(2026, 10, 31), 'CreadoPor': 1, 'AprobadoPor': None}
    class Cursor:
        description = []
        def fetchall(self): return []
    @contextmanager
    def reading(): yield Cursor()
    monkeypatch.setattr(repo, 'transaction', reading)
    monkeypatch.setattr(repo, 'reading', reading, raising=False)
    monkeypatch.setattr(repo, 'profile', lambda cursor: {key: '' for key in repo.PROFILE_KEYS})
    monkeypatch.setattr(repo, 'periods', lambda cursor: [dict(period)])
    monkeypatch.setattr(repo, 'get_period', lambda cursor, identifier: dict(period))
    monkeypatch.setattr(repo, 'history', lambda cursor, identifier: [deepcopy(review)])
    monkeypatch.setattr(repo, 'get_review', lambda cursor, identifier: deepcopy(review))
    monkeypatch.setattr(routes_dgi, 'execute_sp', lambda cursor, *a, **k: cursor)
    def no_snapshot(*args, **kwargs):
        raise AssertionError('Historical or unreadable reviews must not scan fiscal sources')
    monkeypatch.setattr(repo, 'snapshot_base', no_snapshot)
    monkeypatch.setattr(repo, 'snapshot', no_snapshot)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_1'
        session['_fresh'] = True
    return client, review, ENGINE_VERSION


@pytest.mark.parametrize('raw', [json.dumps({'valido': True}), 'invalid-json', '[]'])
def test_dashboard_handles_historical_results_without_scanning_sources(dgi_page, raw):
    client, review, _ = dgi_page
    review['ResultadoJSON'] = raw
    response = client.get('/admin/dgi')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Requiere Revalidación' in html
    assert 'Sin errores bloqueantes' not in html


def test_current_engine_with_unreadable_result_requires_revalidation(dgi_page):
    client, review, engine = dgi_page
    review['Motor'] = engine
    response = client.get('/admin/dgi')
    assert response.status_code == 200
    assert 'Requiere Revalidación' in response.get_data(as_text=True)


def test_historical_review_opens_with_explicit_revalidation(dgi_page):
    client, _, _ = dgi_page
    response = client.get('/admin/dgi/revisiones/11')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Revalidar fuentes' in html
    assert 'histórica' in html
    assert 'Descargar informe validado' not in html


def test_dashboard_does_not_open_mutation_transaction(dgi_page, monkeypatch):
    client, _, _ = dgi_page
    def mutation_forbidden():
        raise AssertionError('Dashboard reads must not hold a serializable mutation transaction')
    monkeypatch.setattr(repo, 'transaction', mutation_forbidden)
    assert client.get('/admin/dgi').status_code == 200


@pytest.mark.parametrize('matching', [True, False])
def test_current_results_still_verify_source_fingerprint(dgi_page, monkeypatch, matching):
    client, review, engine = dgi_page
    review['Motor'] = engine
    review['ResultadoJSON'] = json.dumps({'bloqueantes': 0, 'advertencias': 0, 'hallazgos': [], 'totales': {}})
    # Independently serialized historical fingerprint of the synthetic source.
    review['Huella'] = hashlib.sha256('{"obligacion":"Diagnóstico interno","source_version":1}'.encode()).hexdigest()
    monkeypatch.setattr(repo, 'snapshot_base', lambda cursor, period: {'source_version': 1})
    monkeypatch.setattr(repo, 'snapshot', lambda *a, **k: {'source_version': 1 if matching else 2, 'obligacion': 'Diagnóstico interno'})
    response = client.get('/admin/dgi')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ('Sin errores bloqueantes' in html) is matching
    assert ('Requiere Revalidación' in html) is not matching


def test_read_scope_restores_connection_even_when_rendering_fails(monkeypatch):
    class Cursor:
        def execute(self, *args): return self
        def fetchone(self): return (1,)
        def close(self): pass
    class Connection:
        autocommit = False
        closed = False
        def cursor(self): return Cursor()
        def close(self): self.closed = True
    conn = Connection()
    monkeypatch.setattr(repo, 'get_db_connection', lambda: conn)
    with pytest.raises(RuntimeError, match='render failure'):
        with repo.reading():
            assert conn.autocommit is True
            raise RuntimeError('render failure')
    assert conn.autocommit is False
    assert conn.closed is True


def test_read_scope_closes_pending_results_before_resetting_session(monkeypatch):
    class Connection:
        autocommit = False
        busy = False
        closed = False
        def cursor(self): return Cursor(self)
        def close(self): self.closed = True
    class Cursor:
        def __init__(self, conn): self.conn = conn
        def execute(self, *args):
            if self.conn.busy:
                raise RuntimeError('Connection is busy with results for another command')
            return self
        def fetchone(self):
            self.conn.busy = True
            return (1,)
        def close(self): self.conn.busy = False
    conn = Connection()
    monkeypatch.setattr(repo, 'get_db_connection', lambda: conn)
    with repo.reading():
        pass
    assert not conn.busy and conn.closed
    assert conn.autocommit is False


@pytest.mark.parametrize('readable', [True, False])
def test_revalidation_reuses_only_a_readable_saved_result(monkeypatch, readable):
    from app.services.dgi_engine import ENGINE_VERSION, fingerprint
    source = {'perfil': {}, 'desde': '2026-10-01', 'hasta': '2026-10-31'}
    result = {'bloqueantes': 0, 'advertencias': 0, 'hallazgos': [], 'totales': {}}
    previous = SimpleNamespace(ID=11, Version=1, Huella=fingerprint(source), Motor=ENGINE_VERSION, Estado='BORRADOR')
    monkeypatch.setattr(repo, 'get_period', lambda *a: {'Estado': 'Abierto'})
    monkeypatch.setattr(repo, 'snapshot', lambda *a: source)
    monkeypatch.setattr(repo, 'analyze', lambda *a: result)
    monkeypatch.setattr(repo, 'get_review', lambda *a: {
        'ResultadoJSON': json.dumps(result if readable else {'valido': True}),
        'SnapshotJSON': json.dumps(source),
    })
    class Result:
        def __init__(self, value): self.value = value
        def fetchone(self): return self.value
    def execute(cursor, procedure, *a, **k):
        return Result(previous if procedure.endswith('sp_ObtenerUltimaRevisionDGI') else (12,))
    monkeypatch.setattr(repo, 'execute_sp', execute)
    assert repo.create_review(Result(previous), 7, 'Diagnóstico interno', 1) == (11 if readable else 12)
