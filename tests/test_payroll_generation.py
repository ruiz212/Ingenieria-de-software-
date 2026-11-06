"""Payroll HTTP regressions with synthetic employees and no SQL connection."""
from datetime import date, datetime
from decimal import Decimal
from inspect import unwrap
from types import SimpleNamespace

import pytest
from flask import Flask

from app.admin import routes_hr as hr
from app.services.contabilidad_service import ContabilidadService


class PayrollDB:
    def __init__(self, history):
        self.history = history
        self.rows = []
        self.calls = []
        self.committed = self.rolled_back = self.closed = False
        self.employee = SimpleNamespace(ID=1, UsuarioID=None, NombreCompleto='Empleado sintético',
                                        Cargo='Admin', SalarioBase=Decimal('20000'),
                                        FechaIngreso=date(2025, 1, 1))

    def cursor(self):
        return self

    def sp(self, cursor, name, params=(), **kwargs):
        self.calls.append((name, params))
        results = {
            'seguridad.sp_ObtenerTasasLaboralesConfig': [],
            'rrhh.sp_ListarEmpleadosActivosCompletos': [self.employee],
            'rrhh.sp_ObtenerEmpleadoActivoCompleto': [self.employee],
            'rrhh.sp_ContarEmpleadosActivos': [(1,)],
            'rrhh.sp_ObtenerEmpleadoBloqueo': [(1,)],
            'rrhh.sp_VerificarNominaExistenteMensual': [],
            'rrhh.sp_LimpiarBorradoresNominaPeriodo': [],
            'rrhh.sp_ObtenerHistoricoRentaAnualEmpleado': [self.history],
            'rrhh.sp_ObtenerDeduccionesJudicialesVigentes': [],
            'rrhh.sp_ListarPrestamosActivosEmpleado': [],
            'rrhh.sp_ListarCobrosPerdidasPendientesEmpleado': [],
            'rrhh.sp_ObtenerMetricasAsistenciaPeriodo': [(30, 30, 0)],
            'rrhh.sp_InsertarNominaMensual': [(101,)],
            'rrhh.sp_InsertarNominaBatch': [(101,)],
            'rrhh.sp_ActualizarNominaEstructurada': [],
            'rrhh.sp_InsertarDetalleNomina': [],
        }
        assert name in results, name
        self.rows = list(results[name])

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('previous_ir', ['0', '16000', '19000'])
@pytest.mark.parametrize('fail_posting', [False, True])
def test_accumulated_ir_generation_uses_month_and_previous_withholding_correctly(monkeypatch, batch, previous_ir, fail_posting):
    # November salary 20,000: taxable 18,600, previous taxable income 186,000.
    # Projected annual tax 19,640; due through November 18,003.33.
    db = PayrollDB((Decimal('186000'), Decimal(previous_ir), 10))
    monkeypatch.setattr(hr, 'get_db_connection', lambda: db)
    monkeypatch.setattr(hr, 'execute_sp', db.sp)
    monkeypatch.setattr(hr, 'obtener_dias_ausentes_auto', lambda *args: 0)
    monkeypatch.setattr(hr, 'business_now', lambda: datetime(2026, 11, 6, 10))
    monkeypatch.setattr(hr, 'current_user', SimpleNamespace(id=1))
    posted = []

    def ledger(**kwargs):
        ContabilidadService._validar_partida_doble([(d[0], d[1], d[2]) for d in kwargs['detalles']])
        posted.append(kwargs)
        if fail_posting:
            raise RuntimeError('Synthetic posting failure')
        return {'asiento_id': 1}

    monkeypatch.setattr(ContabilidadService, 'crear_asiento', ledger)
    payload = {'empleado_id': 1, 'periodo_inicio': '2026-11-01', 'periodo_fin': '2026-11-30'}
    app = Flask(__name__)
    with app.test_request_context(json=payload):
        response = unwrap(hr.calcular_nomina_batch if batch else hr.calcular_nomina)()
    if isinstance(response, tuple):
        response, status = response
    else:
        status = response.status_code
    assert status == (500 if fail_posting else 200), response.get_json()
    insertion = next(p for name, p in db.calls if name == ('rrhh.sp_InsertarNominaBatch' if batch else 'rrhh.sp_InsertarNominaMensual'))
    # (204600 / 11 * 12 - 200000) * 20% + 15000 = 19640 annually;
    # 19640 * 11 / 12 = 18003.33, minus previously withheld.
    expected = max(Decimal('0'), Decimal('18003.33') - Decimal(previous_ir))
    assert Decimal(str(insertion[6 if batch else 9])) == expected
    assert posted and db.closed
    assert db.committed is not fail_posting
    assert db.rolled_back is fail_posting
    if fail_posting:
        assert 'Synthetic posting failure' not in response.get_json()['error']
