"""Búsqueda fiscal acotada al período, paginada y sin tocar facturas."""
import calendar
import os
from datetime import date, timedelta

import pyodbc
import pytest

from app import create_app
from app.models import User
from app.qa_safety import connect_qa


@pytest.fixture
def client(monkeypatch):
    class Config:
        TESTING = True
        SECRET_KEY = 'corte5-dgi-test'
        WTF_CSRF_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''

    app = create_app(Config)
    app.login_manager._user_callback = lambda _: User(1, 'qa', 'QA', 1, 'SuperAdmin')
    result = app.test_client()
    with result.session_transaction() as value:
        value['_user_id'] = 'emp_1'
        value['_fresh'] = True
    return result


def test_search_rejects_unbounded_page_size(client):
    response = client.get('/admin/dgi/facturas?periodo=1&tamano=500')
    assert response.status_code == 400


def test_search_forwards_filters_and_returns_page(client, monkeypatch):
    from app.admin import routes_dgi

    seen = {}

    def search(**filters):
        seen.update(filters)
        return {'total': 1, 'facturas': [{'numero': 'FAC-00000030'}]}

    monkeypatch.setattr(routes_dgi.repo, 'search_invoices', search, raising=False)
    response = client.get('/admin/dgi/facturas?periodo=4&buscar=FAC-00000030&estado=Emitida&tipo=Encargo&pagina=2&tamano=25')
    assert response.status_code == 200
    assert response.json['total'] == 1
    assert seen['period_id'] == 4
    assert seen['page'] == 2 and seen['size'] == 25
    assert seen['text'] == 'FAC-00000030'
    assert seen['state'] == 'Emitida' and seen['sale_type'] == 'Encargo'


def test_native_search_finds_an_invoice_without_loading_all_rows():
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    conn = connect_qa(pyodbc.connect, value)
    try:
        cursor = conn.cursor()
        invoice = cursor.execute(
            "SELECT TOP 1 ID,NumeroFactura,FechaHora,EstadoFiscal,EsEncargo FROM ventas.Facturas "
            "WHERE FechaHora IS NOT NULL ORDER BY ID DESC"
        ).fetchone()
        if not invoice:
            pytest.skip('QA sin factura de prueba.')
        stamp = invoice.FechaHora
        first = date(stamp.year, stamp.month, 1)
        last = date(stamp.year, stamp.month, calendar.monthrange(stamp.year, stamp.month)[1])
        period = cursor.execute('SELECT ID FROM fiscal.DGI_Periodos WHERE Desde=? AND Hasta=?', first, last).fetchone()
        if period:
            period_id = period[0]
        else:
            period_id = cursor.execute(
                'INSERT INTO fiscal.DGI_Periodos(Desde,Hasta,CreadoPor) OUTPUT INSERTED.ID VALUES(?,?,?)',
                first, last, 1,
            ).fetchone()[0]
        cursor.execute(
            'EXEC fiscal.sp_ListarFacturasPeriodo ?,?,?,?,?,?,?,?,?',
            period_id, str(invoice.NumeroFactura), str(invoice.EstadoFiscal),
            1 if invoice.EsEncargo else 0, None, None, 1, 10, stamp,
        )
        total = cursor.fetchone()[0]
        assert total >= 1
        assert cursor.nextset()
        rows = cursor.fetchall()
        assert any(row.NumeroFactura == invoice.NumeroFactura for row in rows)
        assert len(rows) <= 10
    finally:
        conn.rollback()
        conn.close()


def test_native_search_filters_customer_date_state_and_sale_type():
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Necesita TEST_DB_CONNECTION_STRING de QA.')
    conn = connect_qa(pyodbc.connect, value)
    try:
        cursor = conn.cursor()
        invoice = cursor.execute(
            'SELECT TOP 1 f.ID,f.FechaHora,f.EstadoFiscal,f.EsEncargo,c.Nombre '
            'FROM ventas.Facturas f JOIN crm.Clientes c ON c.ID=f.ClienteID '
            'WHERE c.Nombre IS NOT NULL AND LEN(c.Nombre)>=3 ORDER BY f.ID DESC'
        ).fetchone()
        if not invoice:
            pytest.skip('QA sin factura con cliente para buscar.')
        stamp = invoice.FechaHora
        day = stamp.date()
        first = date(day.year, day.month, 1)
        last = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])
        period = cursor.execute('SELECT ID FROM fiscal.DGI_Periodos WHERE Desde=? AND Hasta=?', first, last).fetchone()
        period_id = period[0] if period else cursor.execute(
            'INSERT INTO fiscal.DGI_Periodos(Desde,Hasta,CreadoPor) OUTPUT INSERTED.ID VALUES(?,?,?)',
            first, last, 1,
        ).fetchone()[0]
        cursor.execute('EXEC fiscal.sp_ListarFacturasPeriodo ?,?,?,?,?,?,?,?,?',
                       period_id, invoice.Nombre[:3], invoice.EstadoFiscal,
                       invoice.EsEncargo, day, day, 1, 25, stamp - timedelta(hours=1))
        assert cursor.fetchone()[0] >= 1
        assert cursor.nextset()
        rows = cursor.fetchall()
        assert any(row.ID == invoice.ID and row.EsReciente for row in rows)
        assert len(rows) <= 25
        cursor.execute('EXEC fiscal.sp_ListarFacturasPeriodo ?,?,?,?,?,?,?,?,?',
                       period_id, None, invoice.EstadoFiscal, invoice.EsEncargo,
                       day + timedelta(days=1), day + timedelta(days=1), 1, 10, stamp)
        assert cursor.fetchone()[0] == 0
        assert cursor.nextset() and cursor.fetchall() == []
    finally:
        conn.rollback()
        conn.close()
