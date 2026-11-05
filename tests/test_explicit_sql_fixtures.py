"""Native SQL tests must opt into a named QA target, including on CI."""
import importlib.util
from pathlib import Path
import pytest


@pytest.mark.parametrize('filename,fixture', [('test_audit_group4_auth_inv_prod.py', 'qa_conn_str'), ('test_db_schemas_roles_sp_smtp.py', 'app_instance')])
def test_sql_fixture_skips_without_explicit_target(monkeypatch, filename, fixture):
    monkeypatch.delenv('TEST_DB_CONNECTION_STRING', raising=False)
    path = Path(__file__).parent/filename
    spec = importlib.util.spec_from_file_location('review_sql_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def forbidden(*args, **kwargs):
        raise AssertionError('SQL fixture attempted an implicit database connection')
    monkeypatch.setattr(module.pyodbc, 'connect', forbidden)
    with pytest.raises(pytest.skip.Exception):
        next(getattr(module, fixture).__wrapped__())
    import os
    assert 'TEST_DB_CONNECTION_STRING' not in os.environ
