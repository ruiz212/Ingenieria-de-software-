"""Una prueba nunca debe abrir la conexión habitual por accidente."""
from types import SimpleNamespace

import pytest
from flask import Flask
from app import db


@pytest.mark.parametrize('connection_string', [
    'SERVER=localhost;DATABASE=PanaderiaReal;',
    'SERVER=localhost;DSN=normal;',
    'SERVER=localhost;DATABASE=PanaderiaQA_test;DATABASE=Real;',
    '',
])
def test_testing_refuses_non_qa_before_opening_connection(monkeypatch, connection_string):
    attempts=[]
    monkeypatch.setattr(db.pyodbc,'connect',lambda *a,**k:attempts.append(True))
    app=Flask(__name__)
    app.config.update(TESTING=True,SQL_SERVER_CONNECTION_STRING=connection_string)
    with app.app_context(),pytest.raises(ValueError,match='QA'):
        db.get_db_connection()
    assert attempts==[]


def test_testing_checks_actual_database_and_closes_mismatch(monkeypatch):
    closed=[]
    connection=SimpleNamespace(
        cursor=lambda:SimpleNamespace(execute=lambda sql:SimpleNamespace(fetchone=lambda:('Real',))),
        close=lambda:closed.append(True),
    )
    monkeypatch.setattr(db.pyodbc,'connect',lambda *a,**k:connection)
    app=Flask(__name__)
    app.config.update(TESTING=True,SQL_SERVER_CONNECTION_STRING='SERVER=localhost;DATABASE=PanaderiaQA_test;')
    with app.app_context(),pytest.raises(ValueError,match='QA'):
        db.get_db_connection()
    assert closed==[True]


def test_testing_returns_verified_qa_connection(monkeypatch):
    connection=SimpleNamespace(cursor=lambda:SimpleNamespace(execute=lambda sql:SimpleNamespace(fetchone=lambda:('PanaderiaQA_test',))))
    monkeypatch.setattr(db.pyodbc,'connect',lambda *a,**k:connection)
    app=Flask(__name__)
    app.config.update(TESTING=True,SQL_SERVER_CONNECTION_STRING='SERVER=localhost;DATABASE={PanaderiaQA_test};')
    with app.app_context(): assert db.get_db_connection() is connection
