"""Regresiones contables con SQL sustituido únicamente en su frontera."""
import inspect
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import Flask

from app.admin import routes_accounting as routes
from app.services import contabilidad_service as accounting


class AccountingDatabase:
    """Almacén sintético: el default SQL simula UTC al cambiar de mes."""

    def __init__(self, opening=Decimal('100'), movements=()):
        self.opening = opening
        self.movements = movements
        self.expenses = []
        self.journals = []
        self.statements = []
        self.committed = False
        self.closed = False

    def cursor(self):
        return self

    def execute(self, sql, *params):
        if len(params) == 1 and isinstance(params[0], (tuple, list)):
            params = tuple(params[0])
        self.statements.append((sql, params))
        self.rows = []
        if 'INSERT INTO EgresosPrivados' in sql:
            recorded = next((p for p in params if isinstance(p, datetime)), datetime(2026, 11, 1, 4))
            self.expenses.append(recorded)
            self.rows = [(41,)]
        elif 'INSERT INTO AsientosDiario' in sql:
            self.journals.append(params[0])
            self.rows = [(92,)]
        elif 'SELECT ID, Estado FROM PeriodosContables' in sql:
            self.rows = [(7, 'Abierto')]
        elif 'SELECT ID FROM PeriodosContables' in sql:
            self.rows = []  # No existe fila para el mes consultado.
        elif 'UPDATE TiposComprobante' in sql:
            self.rows = [(2, 'EG', 1)]
        elif 'SELECT ID FROM CatalogoCuentas' in sql:
            self.rows = [(6,)]
        elif 'SELECT EsTransaccional' in sql:
            self.rows = [(True,)]
        elif 'SELECT Naturaleza' in sql:
            self.rows = [('Deudora',)]
        elif 'SUM(D.Debe-D.Haber)' in sql:
            self.rows = [(self.opening,)]
        elif 'FROM DetalleAsientos D' in sql:
            self.rows = list(self.movements)
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return self.rows

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False

    def close(self):
        self.closed = True


@pytest.fixture
def route_app(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='synthetic-only')
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=9))
    # Las autorizaciones se prueban por separado; aquí se ejecutan rutas/servicios reales.
    app.add_url_rule('/egresos', view_func=inspect.unwrap(routes.crear_egreso), methods=['POST'])
    app.add_url_rule('/mayor', view_func=inspect.unwrap(routes.libro_mayor))
    monkeypatch.setattr(routes, 'render_template', lambda template, **context: {
        'movimientos': context['movimientos'], 'mes': context['mes'], 'anio': context['anio']})
    return app


def test_expense_and_journal_share_business_timestamp_at_month_boundary(route_app, monkeypatch):
    database = AccountingDatabase()
    monkeypatch.setattr(routes, 'get_db_connection', lambda: database)
    monkeypatch.setattr(routes, 'business_now', lambda: datetime(2026, 10, 31, 22))
    # Un segundo reloj cruzado evidencia que la fecha debe propagarse, no recapturarse.
    monkeypatch.setattr(accounting, 'business_now', lambda: datetime(2026, 11, 1))
    response = route_app.test_client().post('/egresos', json={'concepto': 'Pago sintético', 'monto': '25.50'})
    assert response.status_code == 200
    assert database.expenses == [datetime(2026, 10, 31, 22)]
    assert database.journals == [datetime(2026, 10, 31, 22)]
    assert database.committed and database.closed


def test_expense_service_keeps_optional_date_compatible_with_existing_callers(monkeypatch):
    database = AccountingDatabase()
    monkeypatch.setattr(accounting, 'business_now', lambda: datetime(2026, 10, 17, 9))
    accounting.ContabilidadService.contabilizar_egreso(database, 9, 'Pago', Decimal('5'))
    assert database.journals == [datetime(2026, 10, 17, 9)]


@pytest.mark.parametrize('month,year,end', [('10', '2026', datetime(2026, 10, 31)), ('2', '2028', datetime(2028, 2, 29)), ('12', '2026', datetime(2026, 12, 31))])
def test_ledger_without_period_returns_opening_balance_and_uses_month_dates(route_app, monkeypatch, month, year, end):
    database = AccountingDatabase()
    monkeypatch.setattr(routes, 'get_db_connection', lambda: database)
    response = route_app.test_client().get('/mayor', query_string={'cuenta_codigo': '1.1.01.001', 'mes': month, 'anio': year})
    assert response.status_code == 200
    assert response.json['movimientos'] == [{'Fecha': '', 'Comprobante': '', 'Descripcion': 'Saldo anterior',
        'Referencia': '', 'Debe': 0, 'Haber': 0, 'Saldo': 100.0}]
    movement_queries = [(sql, params) for sql, params in database.statements if 'ORDER BY A.Fecha, A.ID' in sql]
    assert movement_queries
    for sql, params in movement_queries:
        assert 'A.PeriodoID = ?' not in sql
        assert params == ('1.1.01.001', datetime(int(year), int(month), 1), end)
    assert all('INSERT' not in sql and 'UPDATE' not in sql for sql, _ in database.statements)
    assert database.closed


def test_ledger_carries_opening_into_current_movements():
    database = AccountingDatabase(movements=[SimpleNamespace(Fecha=datetime(2026, 10, 3),
        NumeroComprobante='EG-1', DescripcionAsiento='Pago', DescripcionLinea=None,
        Debe=Decimal('0'), Haber=Decimal('25'), ReferenciaExterna='EGR-41')])
    result = accounting.ContabilidadService.obtener_libro_mayor(database, '1.1.01.001',
        fecha_inicio=datetime(2026, 10, 1), fecha_fin=datetime(2026, 10, 31))
    assert [row['Saldo'] for row in result] == [100.0, 75.0]
