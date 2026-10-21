"""A rejected SQL identity must never return the underlying privileged connection."""
import os
from types import SimpleNamespace

import pytest
from flask import Flask, g
from werkzeug.exceptions import ServiceUnavailable

from app import db


class SqlConnection:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.closed = False
        self.rolled_back = False
        self.statements = []

    def cursor(self):
        return self

    def execute(self, sql, *params):
        self.statements.append(sql)
        if self.fail_at == 'identity' and 'EXECUTE AS USER' in sql:
            raise RuntimeError('Synthetic impersonation denied')
        if self.fail_at == 'context' and 'sp_set_session_context' in sql:
            raise RuntimeError('Synthetic context rejected')
        return self

    def commit(self):
        if self.fail_at == 'commit':
            raise RuntimeError('Synthetic commit failure')

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def sql_case(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY='synthetic-only', SQL_SERVER_CONNECTION_STRING='mocked-transport')
    opened = []
    fail_at = [None]

    def connect(*args, **kwargs):
        conn = SqlConnection(fail_at[0])
        opened.append(conn)
        return conn

    monkeypatch.setattr(db.pyodbc, 'Connection', SqlConnection)
    monkeypatch.setattr(db.pyodbc, 'connect', connect)
    user = SimpleNamespace(id=90001, username='synthetic', is_authenticated=True, rol_nombre='Estandar')
    monkeypatch.setattr(db, 'current_user', user)
    return app, opened, fail_at, user


@pytest.mark.parametrize('failure', ['identity', 'commit', 'context'])
def test_sql_security_failure_closes_connection_instead_of_returning_dbo(sql_case, failure):
    app, opened, fail_at, _ = sql_case
    fail_at[0] = failure
    with app.test_request_context('/pos'):
        with pytest.raises(ServiceUnavailable):
            db.get_db_connection()
    assert len(opened) == 1
    assert opened[0].closed
    assert opened[0].rolled_back


def test_unknown_authenticated_role_is_rejected_before_opening_sql(sql_case):
    app, opened, _, user = sql_case
    user.rol_nombre = 'Unknown role'
    with app.test_request_context('/pos'):
        with pytest.raises(ServiceUnavailable):
            db.get_db_connection()
    assert opened == []


def test_user_resolution_failure_does_not_open_privileged_sql(sql_case, monkeypatch):
    app, opened, _, _ = sql_case

    class UnavailableUser:
        def __bool__(self):
            raise RuntimeError('Synthetic user loader failure')

    monkeypatch.setattr(db, 'current_user', UnavailableUser())
    with app.test_request_context('/pos'):
        with pytest.raises(ServiceUnavailable):
            db.get_db_connection()
    assert opened == []


def test_valid_role_is_kept_until_connection_close(sql_case):
    app, opened, _, _ = sql_case
    with app.test_request_context('/pos'):
        conn = db.get_db_connection()
        assert any("EXECUTE AS USER = 'usr_bd_cajero_pos'" in sql for sql in opened[0].statements)
        assert not opened[0].closed
        conn.close()
    assert opened[0].closed
    assert 'REVERT;' in opened[0].statements


def test_failed_commit_attempts_revert_before_closing_security_context(sql_case):
    app, opened, fail_at, _ = sql_case
    fail_at[0] = 'commit'
    with app.test_request_context('/pos'):
        with pytest.raises(ServiceUnavailable):
            db.get_db_connection()
    assert 'REVERT;' in opened[0].statements
    assert opened[0].closed


def test_authentication_bootstrap_explicitly_skips_user_resolution(sql_case, monkeypatch):
    app, opened, _, _ = sql_case

    class UnavailableUser:
        def __bool__(self):
            raise AssertionError('Bootstrap must not reload the user')

    monkeypatch.setattr(db, 'current_user', UnavailableUser())
    with app.test_request_context('/login'):
        g._loading_auth_user = True
        conn = db.get_db_connection(inject_context=False)
        conn.close()
    assert len(opened) == 1
    assert not any('EXECUTE AS' in sql for sql in opened[0].statements)


@pytest.mark.skipif(not os.environ.get('TEST_DB_CONNECTION_STRING'), reason='Requires an explicit PanaderiaQA_ database')
def test_real_qa_connection_is_closed_when_impersonation_is_rejected(monkeypatch):
    from flask_login import LoginManager, login_user
    from app.models import User

    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='synthetic-only', SQL_SERVER_CONNECTION_STRING=os.environ['TEST_DB_CONNECTION_STRING'])
    LoginManager(app)
    connect = db.pyodbc.connect
    opened = []

    def capture(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    def reject(*args, **kwargs):
        raise db.pyodbc.ProgrammingError('Synthetic EXECUTE AS rejection on a real QA connection')

    monkeypatch.setattr(db.pyodbc, 'connect', capture)
    monkeypatch.setattr(db, 'as_db_role', reject)
    with app.test_request_context('/pos'):
        login_user(User(90001, 'synthetic', 'Synthetic Only', 1, 'Estandar'))
        with pytest.raises(ServiceUnavailable):
            db.get_db_connection()
    assert len(opened) == 1
    with pytest.raises(db.pyodbc.ProgrammingError):
        opened[0].cursor()
