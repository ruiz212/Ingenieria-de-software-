"""Las pantallas nuevas renderizan con el esquema y rol reales de QA."""
import os

import pyodbc
import pytest

from app import create_app
from app.models import User
from app.qa_safety import connect_qa
from app.services.business_time import business_now
from config import Config


def test_hr_and_dgi_pages_render_with_real_qa_role():
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    connection = connect_qa(pyodbc.connect, value)
    try:
        period = connection.cursor().execute('SELECT TOP 1 ID FROM fiscal.DGI_Periodos ORDER BY ID DESC').fetchone()
    finally:
        connection.rollback()
        connection.close()
    if not period:
        pytest.skip('QA sin período DGI.')

    class QAConfig(Config):
        TESTING = True
        SECRET_KEY = 'corte5-pages-test'
        SQL_SERVER_CONNECTION_STRING = value
        WTF_CSRF_ENABLED = False

    app = create_app(QAConfig)
    app.login_manager._user_callback = lambda _: User(1, 'qa', 'QA', 1, 'SuperAdmin')
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_1'
        session['_fresh'] = True

    hr = client.get('/admin/rrhh')
    assert hr.status_code == 200
    assert f'value="{business_now():%Y-%m-%d}"' in hr.text
    assert 'Perfiles de puesto' in hr.text
    dgi = client.get(f'/admin/dgi?periodo={period[0]}')
    assert dgi.status_code == 200
    assert 'Facturas del período' in dgi.text
    result = client.get(f'/admin/dgi/facturas?periodo={period[0]}&tamano=10')
    assert result.status_code == 200
    assert len(result.json['facturas']) <= 10
    missing = client.get('/admin/dgi/facturas?periodo=2147483647')
    assert missing.status_code == 404
