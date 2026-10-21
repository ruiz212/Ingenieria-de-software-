"""Synthetic SQL and face boundaries; no camera or biometric data is used."""
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from flask import Flask


class AttendanceDB:
    def __init__(self, entry=None, exit=None):
        self.attendance = SimpleNamespace(ID=7, HoraEntrada=entry, HoraSalida=exit) if entry else None
        self.writes = []
        self.closed = False

    def cursor(self):
        return self

    def execute(self, sql, *args):
        self.sql = sql
        if 'INSERT INTO Asistencia' in sql:
            self.attendance = SimpleNamespace(ID=7, HoraEntrada=time.fromisoformat(args[3]), HoraSalida=None)
            self.writes.append('entrada')
        elif 'UPDATE Asistencia SET HoraSalida' in sql:
            self.attendance.HoraSalida = time.fromisoformat(args[0])
            self.writes.append('salida')
        return self

    def fetchone(self):
        if 'FROM Empleados' in self.sql:
            return SimpleNamespace(ID=1, NombreCompleto='Persona sintética', HoraEntrada=time(8), HoraSalida=time(17))
        if 'FROM TurnosLaborales' in self.sql:
            return SimpleNamespace(ID=1, HoraEntrada=time(8), ToleranciaMinutos=15)
        if 'FROM Asistencia' in self.sql:
            return self.attendance
        raise AssertionError(self.sql)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def kiosk(monkeypatch):
    with patch('pyodbc.connect', side_effect=AssertionError('Real SQL forbidden')):
        from app.kiosco import routes
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.add_url_rule('/recognize', view_func=routes.reconocer, methods=['POST'])
    monkeypatch.setattr(routes.face_service, 'reconocer_rostro', lambda *_a, **_k: {'status': 'match', 'empleado_id': 1})
    clock = lambda: datetime(2026, 7, 1, 8)
    monkeypatch.setattr(routes, 'business_now', clock, raising=False)
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return clock()
    monkeypatch.setattr(routes, 'datetime', FixedDatetime)
    return app.test_client(), routes


def test_repeated_frames_are_idempotent_entry_not_automatic_exit(kiosk, monkeypatch):
    client, routes = kiosk
    db = AttendanceDB()
    monkeypatch.setattr(routes, 'get_db_connection', lambda: db)
    first = client.post('/recognize', json={'image': 'synthetic-frame'})
    second = client.post('/recognize', json={'image': 'synthetic-frame'})
    assert first.json['tipo'] == 'entrada'
    assert db.attendance.HoraSalida is None
    assert second.json['tipo'] == 'entrada'
    assert db.writes == ['entrada']


def test_explicit_exit_cannot_create_an_entry(kiosk, monkeypatch):
    client, routes = kiosk
    db = AttendanceDB()
    monkeypatch.setattr(routes, 'get_db_connection', lambda: db)
    response = client.post('/recognize', json={'image': 'synthetic-frame', 'accion': 'salida'})
    assert response.status_code == 409
    assert db.attendance is None


def test_explicit_exit_respects_server_minimum_interval(kiosk, monkeypatch):
    client, routes = kiosk
    db = AttendanceDB(time(7, 59, 1))
    monkeypatch.setattr(routes, 'get_db_connection', lambda: db)
    response = client.post('/recognize', json={'image': 'synthetic-frame', 'accion': 'salida'})
    assert response.status_code == 409
    assert db.attendance.HoraSalida is None


def test_exit_at_minimum_interval_and_retries_write_once(kiosk, monkeypatch):
    client, routes = kiosk
    db = AttendanceDB(time(7, 59))
    monkeypatch.setattr(routes, 'get_db_connection', lambda: db)
    for _ in range(2):
        response = client.post('/recognize', json={'image': 'synthetic-frame', 'accion': 'salida'})
        assert response.status_code == 200
        assert response.json['tipo'] == 'salida'
    assert db.writes == ['salida']


@pytest.mark.parametrize('payload', [None, [], {'image': 'synthetic-frame', 'accion': 'toggle'}])
def test_malformed_or_invalid_operation_is_rejected(kiosk, payload):
    client, _ = kiosk
    assert client.post('/recognize', json=payload).status_code == 400


def test_administrative_exit_uses_same_minimum_interval(monkeypatch):
    from inspect import unwrap
    from app.admin import routes_hr
    db = AttendanceDB(time(7, 59, 1))
    app = Flask(__name__)
    app.add_url_rule('/mark', view_func=unwrap(routes_hr.kiosco_marcar), methods=['POST'])
    monkeypatch.setattr(routes_hr, 'get_db_connection', lambda: db)
    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 7, 1, 8), raising=False)
    response = app.test_client().post('/mark', json={'empleado_id': 1, 'tipo': 'salida'})
    assert response.status_code == 409
    assert db.attendance.HoraSalida is None


def test_frontend_sends_selected_operation_once_and_never_rearms_itself():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed to execute the kiosk JavaScript')
    template = (Path(__file__).resolve().parents[1] / 'templates' / 'kiosco.html').read_text(encoding='utf-8')
    script = re.findall(r'<script>(.*?)</script>', template, re.S)[0]
    harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
        listeners: {}, classList: {add(){}, remove(){}},
        addEventListener(event, fn) { this.listeners[event] = fn; },
        setAttribute(){}, getContext(){ return {drawImage(){}}; },
        toDataURL(){ return 'synthetic-frame'; },
        replaceChildren(){}, appendChild(){},
    });
    return nodes.get(id);
}
const requests = [], timers = [];
const context = vm.createContext({console, Date, setInterval(){return 1;}, clearInterval(){},
    setTimeout(fn){timers.push(fn);},
    document: {getElementById: node, createElement: node, createTextNode: text => text},
    window: {addEventListener(){}},
    fetch: async (_url, options) => {
        requests.push(JSON.parse(options.body));
        return {ok: true, json: async () => ({status:'success', tipo:'salida', mensaje:'Registrada'})};
    },
});
vm.runInContext(SCRIPT, context);
(async () => {
    await vm.runInContext('processFrame()', context);
    assert.equal(requests.length, 0, 'No operation should run before selection');
    assert.ok(node('markExit').listeners.click, 'Exit must have an explicit action');
    node('markExit').listeners.click();
    await vm.runInContext('processFrame()', context);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].accion, 'salida');
    for (const fn of timers.splice(0)) fn();
    await vm.runInContext('processFrame()', context);
    assert.equal(requests.length, 1, 'Timers must not repeat the operation');
    node('markEntry').listeners.click();
    await vm.runInContext('processFrame()', context);
    assert.equal(requests[1].accion, 'entrada');
})().catch(error => {console.error(error); process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', 'const SCRIPT=' + __import__('json').dumps(script) + ';\n' + harness],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
