from datetime import date
from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, jsonify


def leave(start, end, days, kind='Vacaciones'):
    return SimpleNamespace(FechaInicio=date.fromisoformat(start), FechaFin=date.fromisoformat(end),
                           DiasOtorgados=days, TipoLicencia=kind, PagoEmpleador=100, PagoINSS=0)


class HRDB:
    def __init__(self, attendance=(), licenses=(), start=date(2025, 1, 1), end=None, used=True):
        self.attendance = attendance
        self.licenses = licenses
        self.emp = SimpleNamespace(ID=1, NombreCompleto='Persona sintética', SalarioBase=30000,
                                   FechaIngreso=start, FechaEgreso=end)
        self.used = used
        self.closed = False

    def cursor(self):
        return self

    def execute(self, sql, *args):
        self.sql = sql
        self.args = args
        return self

    def fetchone(self):
        if 'FROM Empleados' in self.sql:
            return self.emp
        if 'COUNT(DISTINCT Fecha)' in self.sql:
            return (len(set(self.attendance)),)
        if 'COUNT(*) FROM Asistencia' in self.sql:
            return (int(self.used),)
        raise AssertionError(self.sql)

    def fetchall(self):
        if 'FROM LicenciasEmpleados' in self.sql:
            return self.licenses
        if 'FROM Asistencia' in self.sql:
            return [SimpleNamespace(Fecha=d) for d in self.attendance]
        if 'FROM Nomina' in self.sql:
            return []
        raise AssertionError(self.sql)

    def close(self):
        self.closed = True


@pytest.fixture
def hr():
    with patch('pyodbc.connect', side_effect=AssertionError('Real SQL forbidden')):
        from app.admin import routes_hr
    return routes_hr


def test_attendance_and_license_overlap_reduce_absence_only_once(hr):
    db = HRDB([date(2026, 7, 1)], [leave('2026-07-01', '2026-07-01', 1)])
    assert hr.obtener_dias_ausentes_auto(db, 1, '2026-07-01', '2026-07-31') == 26


def test_sunday_and_outside_employment_marks_do_not_hide_absences(hr):
    db = HRDB([date(2026, 7, 5), date(2026, 7, 1), date(2026, 8, 1)],
              start=date(2026, 7, 20), end=date(2026, 7, 25))
    assert hr.obtener_dias_ausentes_auto(db, 1, date(2026, 7, 1), date(2026, 7, 31)) == 6


def test_license_overlap_and_period_clipping_do_not_double_count(hr):
    db = HRDB([], [leave('2026-06-28', '2026-07-03', 6), leave('2026-07-02', '2026-07-06', 5)])
    assert hr.obtener_dias_ausentes_auto(db, 1, '2026-07-01', '2026-07-31') == 22


def test_unused_attendance_module_retains_no_penalty_safeguard(hr):
    assert hr.obtener_dias_ausentes_auto(HRDB(used=False), 1, '2026-07-01', '2026-07-31') == 0


@pytest.fixture
def liquidation(hr, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='synthetic')
    app.add_url_rule('/calculate', view_func=unwrap(hr.calcular_liquidacion), methods=['POST'])
    app.add_url_rule('/report', view_func=unwrap(hr.reporte_liquidacion))
    monkeypatch.setattr(hr, 'render_template', lambda _template, **data: jsonify(data['liquidacion']))
    return app.test_client(), hr


def test_consumed_vacation_is_not_paid_twice_in_api_or_report(liquidation, monkeypatch):
    client, hr = liquidation
    db = HRDB(licenses=[leave('2025-07-01', '2025-07-30', 30)])
    monkeypatch.setattr(hr, 'get_db_connection', lambda: db)
    api = client.post('/calculate', json={'empleado_id': 1, 'fecha_egreso': '2026-01-01'})
    report = client.get('/report?empleado_id=1&fecha_egreso=2026-01-01')
    assert api.status_code == report.status_code == 200
    assert api.json['liquidacion']['vacaciones']['dias'] == 0
    assert api.json['liquidacion']['vacaciones']['monto_bruto'] == 0
    assert api.json['liquidacion']['aguinaldo']['monto'] == 2630.14
    assert api.json['liquidacion']['indemnizacion']['monto_bruto'] == 30000
    assert api.json['liquidacion']['total_liquidacion'] == 32630.14
    assert report.json == api.json['liquidacion']
    assert db.closed


@pytest.mark.parametrize('licenses, expected', [
    ([], 30),
    ([leave('2026-02-01', '2026-02-15', 15)], 30),
    ([leave('2025-12-28', '2026-01-06', 10)], 25),
    ([leave('2025-07-01', '2025-07-30', 60)], 0),
    ([leave('2025-07-01', '2025-07-30', 30, 'Enfermedad Comun')], 30),
    ([leave('2024-12-27', '2025-01-05', 10)], 25),
])
def test_vacation_consumption_is_clipped_to_employment_and_cutoff(liquidation, monkeypatch, licenses, expected):
    client, hr = liquidation
    monkeypatch.setattr(hr, 'get_db_connection', lambda: HRDB(licenses=licenses))
    response = client.post('/calculate', json={'empleado_id': 1, 'fecha_egreso': '2026-01-01'})
    assert response.status_code == 200
    assert response.json['liquidacion']['vacaciones']['dias'] == expected


def test_exit_before_hire_date_is_validation_error(liquidation, monkeypatch):
    client, hr = liquidation
    monkeypatch.setattr(hr, 'get_db_connection', HRDB)
    assert client.post('/calculate', json={'empleado_id': 1, 'fecha_egreso': '2024-12-31'}).status_code == 400


def test_sunday_only_period_has_no_absences(hr):
    assert hr.obtener_dias_ausentes_auto(HRDB(), 1, '2026-07-05', '2026-07-05') == 0


def test_month_before_employment_has_no_absences(hr):
    assert hr.obtener_dias_ausentes_auto(HRDB(start=date(2026, 8, 1)), 1, '2026-07-01', '2026-07-31') == 0
