"""Dashboard contracts against synthetic SQL rows; no external DB is opened.

The adapter translates only T-SQL syntax. SQLite executes the production WHERE
clauses so a date/fiscal regression changes actual results, not mock returns.
"""
from datetime import date, datetime
import re
import sqlite3

import pytest
from flask import template_rendered

from app import create_app
from app.admin import routes_dashboard as routes
from app.models import User


class SqlRow:
    def __init__(self, cursor, values):
        self.values = values
        self.columns = {column[0]: value for column, value in zip(cursor.description, values)}

    def __getitem__(self, index):
        return self.values[index]

    def __getattr__(self, name):
        return self.columns[name]


class SyntheticDatabase:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = SqlRow
        self.db.executescript('''
            CREATE TABLE Facturas (ID INTEGER PRIMARY KEY, Total NUMERIC, EstadoFiscal TEXT, FechaHora TEXT);
            CREATE TABLE Encargos (FacturaID INTEGER, Estado TEXT, FechaEntrega TEXT);
            CREATE TABLE DetalleFacturas (FacturaID INTEGER, ProductoID INTEGER, Cantidad NUMERIC, Subtotal NUMERIC);
            CREATE TABLE Productos (ID INTEGER, Nombre TEXT, CategoriaID INTEGER);
            CREATE TABLE Categorias (ID INTEGER, Nombre TEXT);
            CREATE TABLE TurnosCaja (ID INTEGER, UsuarioID INTEGER, FechaApertura TEXT, Cerrado INTEGER);
            CREATE TABLE Usuarios (ID INTEGER, NombreCompleto TEXT);
        ''')
        self.result = None
        self.closed = False

    def add_order(self, invoice_day, state='Pendiente', fiscal='Emitida', delivery='2026-10-18', total=100):
        invoice = self.db.execute('INSERT INTO Facturas(Total,EstadoFiscal,FechaHora) VALUES(?,?,?)',
                                  (total, fiscal, invoice_day)).lastrowid
        self.db.execute('INSERT INTO Encargos VALUES(?,?,?)', (invoice, state, delivery))

    def cursor(self):
        return self

    def execute(self, query, *args):
        query = re.sub(r'\bISNULL\(', 'IFNULL(', query, flags=re.I)
        query = re.sub(r'CONVERT\(date,\s*([\w.]+)\)', r'date(\1)', query, flags=re.I)
        top = re.search(r'\bTOP (\d+) ', query, flags=re.I)
        if top:
            query = re.sub(r'\bTOP \d+ ', '', query, count=1, flags=re.I) + f' LIMIT {top[1]}'
        params = tuple(arg.isoformat() if isinstance(arg, (date, datetime)) else arg for arg in args)
        self.result = self.db.execute(query, params)
        return self

    def fetchone(self):
        return self.result.fetchone()

    def fetchall(self):
        return self.result.fetchall()

    def close(self):
        self.closed = True


@pytest.fixture
def dashboard_case(monkeypatch):
    class Config:
        TESTING = True
        SECRET_KEY = 'synthetic-dashboard'
        WTF_CSRF_ENABLED = True
        SQL_SERVER_CONNECTION_STRING = ''

    app = create_app(Config)
    database = SyntheticDatabase()
    monkeypatch.setattr(routes, 'get_db_connection', lambda: database)
    # At this instant UTC has already changed date, Nicaragua has not.
    monkeypatch.setattr(routes, 'business_now', lambda: datetime(2026, 10, 18, 23, 59, 59))
    actor = User(90001, 'synthetic', 'Synthetic', 1, 'Admin')
    monkeypatch.setattr(app.login_manager, '_user_callback', lambda _: actor)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = actor.get_id()
        session['_fresh'] = True
    contexts = []

    def capture(sender, template, context, **extra):
        contexts.append(context)

    def read():
        with template_rendered.connected_to(capture, app):
            response = client.get('/admin/dashboard')
        assert response.status_code == 200
        assert database.closed
        return contexts[-1]['metricas'], response.text

    yield database, read
    database.db.close()


def test_historical_pending_and_ready_orders_remain_visible_without_sales_today(dashboard_case):
    database, read = dashboard_case
    database.add_order('2026-10-14 12:00', delivery='2026-10-15')
    database.add_order('2026-10-16 12:00', state='Listo', delivery='2026-10-17')
    metrics, html = read()
    assert metrics['ventas_hoy'] == 0
    assert metrics['encargos_pendientes'] == 2
    assert metrics['encargos_listos'] == 1
    assert metrics['encargos_atrasados'] == 2
    assert 'Encargos por entregar' in html
    assert '1 listo · 2 atrasados' in html
    assert 'Todos los días' in html
    assert '100%' not in html


def test_no_orders_does_not_claim_a_hundred_percent_delivered(dashboard_case):
    metrics, html = dashboard_case[1]()
    assert metrics['encargos_pendientes'] == 0
    assert metrics['encargos_listos'] == 0
    assert metrics['encargos_atrasados'] == 0
    assert '100%' not in html
    assert 'Encargos por entregar' in html


def test_all_active_states_count_globally_but_delivered_and_voided_do_not(dashboard_case):
    database, read = dashboard_case
    database.add_order('2026-10-10', delivery='2026-10-18')
    database.add_order('2026-10-11', state='En Proceso', delivery='2026-10-19')
    database.add_order('2026-10-12', state='Listo', delivery='2026-10-18')
    database.add_order('2026-10-13', state='Entregado', delivery='2026-10-14')
    database.add_order('2026-10-14', fiscal='Anulada', delivery='2026-10-15')
    # SQL's != predicate excludes unknown state, matching the kitchen monitor.
    database.add_order('2026-10-18', state=None, delivery='2026-10-15')
    metrics, _ = read()
    assert metrics['encargos_pendientes'] == 3
    assert metrics['encargos_listos'] == 1
    assert metrics['encargos_atrasados'] == 0


@pytest.mark.parametrize('fiscal,expected', [('Emitida', 1), (None, 1), ('Anulada', 0)])
def test_operational_fiscal_scope_matches_monitor(dashboard_case, fiscal, expected):
    database, read = dashboard_case
    database.add_order('2026-10-18', fiscal=fiscal, delivery='2026-10-17')
    metrics, _ = read()
    assert metrics['encargos_pendientes'] == expected
    assert metrics['encargos_atrasados'] == expected


@pytest.mark.parametrize('delivery,overdue', [
    ('2026-10-17 23:59:59', 1),
    ('2026-10-18 00:00:00', 0),
    ('2026-10-18 23:59:59', 0),
    ('2026-10-19 00:00:00', 0),
    (None, 0),
])
def test_overdue_uses_delivery_day_in_nicaragua_not_invoice_day(dashboard_case, delivery, overdue):
    database, read = dashboard_case
    database.add_order('2026-10-10', state='Listo', delivery=delivery)
    metrics, _ = read()
    assert metrics['encargos_pendientes'] == 1
    assert metrics['encargos_atrasados'] == overdue


def test_daily_sales_keep_nicaragua_invoice_date_while_orders_are_global(dashboard_case):
    database, read = dashboard_case
    database.add_order('2026-10-17 23:59:59', delivery='2026-10-18', total=10)
    database.add_order('2026-10-18 00:00:00', delivery='2026-10-18', total=20)
    database.add_order('2026-10-18 23:59:59', delivery='2026-10-19', total=30)
    database.add_order('2026-10-19 00:00:00', delivery='2026-10-19', total=40)
    database.add_order('2026-10-18', fiscal='Anulada', total=50)
    metrics, _ = read()
    assert metrics['ventas_hoy'] == 50
    assert metrics['ticket_promedio'] == 25
    assert metrics['encargos_pendientes'] == 4
