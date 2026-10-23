"""Perfiles de puesto y marcaje de contingencia sin cambiar salarios."""
import os
from datetime import datetime, timezone
from inspect import unwrap
from types import SimpleNamespace
from uuid import uuid4

import pyodbc
import pytest
from flask import Flask

from app import create_app
from app.db import as_db_role
from app.models import User
from app.qa_safety import connect_qa


@pytest.fixture
def client():
    class Config:
        TESTING = True
        SECRET_KEY = 'corte5-hr-test'
        WTF_CSRF_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''

    app = create_app(Config)
    app.login_manager._user_callback = lambda _: User(1, 'qa', 'QA', 1, 'SuperAdmin')
    result = app.test_client()
    with result.session_transaction() as value:
        value['_user_id'] = 'emp_1'
        value['_fresh'] = True
    return result


def test_manual_attendance_requires_explanation_before_database(client):
    response = client.post('/kiosco/api/marcar', json={'empleado_id': 1, 'accion': 'entrada'})
    assert response.status_code == 400
    assert 'motivo' in response.json['error'].lower()


def test_profile_route_requires_all_contractual_fields(client):
    response = client.post('/admin/api/rrhh/puestos', json={
        'cargo': 'Panadero', 'perfil_puesto': 'Produce pan',
        'obligaciones': '', 'requisitos_competencias': 'Horno',
    })
    assert response.status_code == 400
    assert 'obligaciones' in response.json['error'].lower()


def test_manual_attendance_writes_reason_and_supervisor_in_same_transaction(client, monkeypatch):
    from app.kiosco import routes

    calls = []
    class Cursor:
        current = None
        def fetchone(self):
            return self.current

    cursor = Cursor()
    class Connection:
        def cursor(self): return cursor
        def commit(self): calls.append('COMMIT')
        def rollback(self): calls.append('ROLLBACK')
        def close(self): pass

    def execute(cursor, name, args=(), **kwargs):
        calls.append((name, args))
        if name == 'rrhh.sp_ObtenerEmpleadoActivoPorIDBloqueo':
            cursor.current = SimpleNamespace(ID=9, NombreCompleto='QA Empleado')
        elif name == 'rrhh.sp_ObtenerTurnoLaboralActivoDefecto':
            cursor.current = SimpleNamespace(ID=1, HoraEntrada=None, ToleranciaMinutos=0)
        elif name == 'rrhh.sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo':
            cursor.current = None
        return cursor

    monkeypatch.setattr(routes, 'get_db_connection', Connection)
    monkeypatch.setattr(routes, 'execute_sp', execute)
    response = client.post('/kiosco/api/marcar', json={
        'empleado_id': 9, 'accion': 'entrada',
        'motivo': 'El empleado no puede usar el reconocimiento facial hoy.',
    })
    assert response.status_code == 200
    audit = [entry for entry in calls if isinstance(entry, tuple) and entry[0] == 'seguridad.sp_RegistrarAuditoria']
    assert len(audit) == 1
    assert 'reconocimiento facial' in audit[0][1][5]
    assert calls.index(audit[0]) < calls.index('COMMIT')


def test_profile_catalog_is_idempotent_in_qa_only():
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    connection = connect_qa(pyodbc.connect, value)
    try:
        cursor = connection.cursor()
        name = f'QA Perfil Corte5 {datetime.now(timezone.utc).timestamp():.0f}'
        cursor.execute('EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
                       name, 'Perfil de prueba', 'Tarea de prueba',
                       'Competencia de prueba', 1, '127.0.0.1')
        cursor.execute('EXEC rrhh.sp_ListarPerfilesPuesto')
        profiles = cursor.fetchall()
        assert any(row.Cargo == name and row.Obligaciones == 'Tarea de prueba' for row in profiles)
        cursor.execute('EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
                       name, 'Perfil actualizado', 'Tarea de prueba',
                       'Competencia de prueba', 1, '127.0.0.1')
        assert cursor.execute('SELECT COUNT(*) FROM rrhh.PerfilesPuesto WHERE Cargo=?', name).fetchone()[0] == 1
    finally:
        connection.rollback()
        connection.close()


def test_native_supervisor_mark_and_audit_commit_together(monkeypatch):
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    from app.kiosco import routes

    connection = connect_qa(pyodbc.connect, value)
    cursor = connection.cursor()
    marker = uuid4().hex[:12]
    try:
        cursor.execute(
            'EXEC rrhh.sp_CrearEmpleado ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?',
            'QA Contingencia', f'QA-{marker}', None, None, None, None,
            None, None, 'QA Puesto', datetime.now().date(), 'Indefinido',
            None, 'Diurna', 100, 'Mensual', 1, None, None, None, None,
        )
        employee_id = cursor.fetchone()[0]

        class Borrowed:
            def cursor(self): return connection.cursor()
            def commit(self): pass
            def rollback(self): connection.rollback()
            def close(self): pass

        monkeypatch.setattr(routes, 'get_db_connection', Borrowed)
        monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.add_url_rule('/manual', view_func=unwrap(routes.marcar_asistencia), methods=['POST'])
        with as_db_role(cursor, 'Admin'):
            response = app.test_client().post('/manual', json={
                'empleado_id': employee_id, 'accion': 'entrada',
                'motivo': 'Fallo verificable de reconocimiento facial.',
            })
        assert response.status_code == 200
        assert cursor.execute('SELECT COUNT(*) FROM rrhh.Asistencia WHERE EmpleadoID=?', employee_id).fetchone()[0] == 1
        audit = cursor.execute(
            "SELECT DatosDespues FROM seguridad.AuditLog WHERE Accion='ASISTENCIA_EXCEPCION' "
            "AND Entidad='Asistencia' AND EntidadID=?", employee_id,
        ).fetchone()
        assert audit and 'Fallo verificable' in audit[0]
    finally:
        connection.rollback()
        connection.close()


def test_native_employee_can_be_registered_without_face_with_default_hire_date(monkeypatch):
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    from app.admin import routes_hr
    from app.services.business_time import business_now

    connection = connect_qa(pyodbc.connect, value)
    cursor = connection.cursor()
    marker = uuid4().hex[:12]
    cargo = f'QA Cargo {marker}'
    try:
        cursor.execute('EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
                       cargo, 'Rol QA', 'Obligaciones QA', 'Competencias QA', 1, '127.0.0.1')

        class Borrowed:
            def cursor(self): return connection.cursor()
            def commit(self): pass
            def rollback(self): connection.rollback()
            def close(self): pass

        monkeypatch.setattr(routes_hr, 'get_db_connection', Borrowed)
        monkeypatch.setattr(routes_hr, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.add_url_rule('/empleado', view_func=unwrap(routes_hr.crear_empleado), methods=['POST'])
        with as_db_role(cursor, 'Admin'):
            response = app.test_client().post('/empleado', json={
                'nombre': 'QA Sin Foto', 'cedula': f'QA-{marker}',
                'cargo': cargo, 'salario_base': 100,
            })
        assert response.status_code == 200
        employee = cursor.execute(
            'SELECT FechaIngreso,FaceDescriptor FROM rrhh.Empleados WHERE Cedula=?', f'QA-{marker}'
        ).fetchone()
        assert employee and employee[0] == business_now().date()
        assert employee[1] is None
    finally:
        connection.rollback()
        connection.close()
