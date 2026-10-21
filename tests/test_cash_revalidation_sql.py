"""R3–R5 regressions against native SQL Server; owned rows always roll back."""
import os
from datetime import datetime
from inspect import unwrap
from types import SimpleNamespace
from uuid import uuid4

import pyodbc
import pytest
from flask import Flask

from app.db import as_db_role
from app.qa_safety import connect_qa
from app.services.contabilidad_service import ContabilidadService
from app.monitor import routes as monitor


class RouteTransaction:
    """Borrow the owned fixture transaction; route commits never persist test rows."""
    def __init__(self, connection):
        self.connection = connection
        self.route_cursor=connection.cursor()
        self.route_cursor.execute('SAVE TRANSACTION cash_route')

    def cursor(self):
        return self.route_cursor

    def commit(self):
        pass

    def rollback(self):
        self.route_cursor.execute('ROLLBACK TRANSACTION cash_route')

    def close(self):
        self.route_cursor.close()


def delivery_client(monkeypatch, conn, user, role):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.add_url_rule('/deliver/<codigo>',view_func=unwrap(monitor.actualizar_estado),methods=['PUT'])
    monkeypatch.setattr(monitor,'get_db_connection',lambda:RouteTransaction(conn))
    monkeypatch.setattr(monitor,'current_user',SimpleNamespace(id=user,rol_nombre=role))
    from app.services import smtp_alerts
    monkeypatch.setattr(smtp_alerts,'notify_error',lambda *a,**k:False)
    return app.test_client()


@pytest.fixture
def sql_cash():
    connection_string = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not connection_string:
        pytest.skip('Explicit QA SQL Server connection required')
    conn = connect_qa(pyodbc.connect, connection_string)
    cur = conn.cursor()
    marker = 'cash_' + uuid4().hex[:14]
    role = cur.execute('SELECT TOP 1 ID FROM seguridad.Roles ORDER BY ID').fetchone()[0]
    user = cur.execute('INSERT INTO seguridad.Usuarios(NombreCompleto,Username,PasswordHash,RolID,Activo) OUTPUT INSERTED.ID VALUES(?,?,?,?,1)',marker,marker,'synthetic-disabled',role).fetchone()[0]
    shift = cur.execute("INSERT INTO ventas.TurnosCaja(UsuarioID,FechaApertura,Cerrado) OUTPUT INSERTED.ID VALUES(?,GETDATE(),0)", user).fetchone()[0]
    invoice = cur.execute("INSERT INTO ventas.Facturas(NumeroFactura,CodigoSeguimiento,UsuarioID,ClienteID,TurnoID,Subtotal,IVA,Total,EsEncargo,IncluyeRUC,EstadoFiscal) OUTPUT INSERTED.ID VALUES(?,?,?,1,?,50,0,50,1,0,'Emitida')", marker, marker[-10:], user, shift).fetchone()[0]
    cur.execute("INSERT INTO ventas.Encargos(FacturaID,FechaEntrega,Estado) VALUES(?,GETDATE(),'Listo')", invoice)
    cur.execute("EXEC sys.sp_set_session_context @key=N'usuario_id',@value=?", user)
    try:
        yield conn, cur, user, shift, invoice, marker
    finally:
        conn.rollback()
        assert conn.cursor().execute('SELECT COUNT(*) FROM ventas.Facturas WHERE NumeroFactura=?', marker).fetchone()[0] == 0
        conn.rollback()
        conn.close()


def test_native_voided_order_lookup_and_compare_reject(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    cur.execute("UPDATE ventas.Facturas SET EstadoFiscal='Anulada' WHERE ID=?", invoice)
    with as_db_role(cur, 'Operativo'):
        cur.execute('EXEC produccion.sp_ObtenerEncargoPorCodigoBloqueo ?', marker[-10:])
        row = cur.fetchone()
        assert row is None or getattr(row, 'EstadoFiscal', None) == 'Anulada'
        cur.execute('EXEC produccion.sp_ActualizarEstadoEncargoCompare ?,?,?', 'Entregado', marker[-10:], 'Listo')
    assert cur.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?', invoice).fetchone()[0] == 'Listo'


def test_native_cashier_books_journal_through_encapsulated_metadata(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    with as_db_role(cur, 'Operativo'):
        assert cur.execute("SELECT HAS_PERMS_BY_NAME('fiscal.sp_RegistrarBitacoraFiscal','OBJECT','EXECUTE')").fetchone()[0] == 0
        assert cur.execute("SELECT HAS_PERMS_BY_NAME('ventas.sp_InsertarPagoSaldoEncargo','OBJECT','EXECUTE')").fetchone()[0] == 0
    with as_db_role(cur, 'Estandar'):
        result = ContabilidadService.contabilizar_cobro_encargo(cur, user, marker, 50, 'Efectivo', fecha=datetime(2026,10,20,12))
    row = cur.execute('SELECT EmisorJSON FROM contabilidad.AsientosDiario WHERE ID=?', result['asiento_id']).fetchone()
    assert row and row[0] and row[0].startswith('{')
    assert cur.execute("SELECT COUNT(*) FROM fiscal.BitacoraFiscal WHERE Entidad='AsientosDiario' AND EntidadID=? AND Accion='ASIENTO'", result['asiento_id']).fetchone()[0] == 1


def test_native_operativo_inventory_purchase_can_book_without_fiscal_grant(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    with as_db_role(cur,'Operativo'):
        assert cur.execute("SELECT HAS_PERMS_BY_NAME('fiscal.sp_RegistrarBitacoraFiscal','OBJECT','EXECUTE')").fetchone()[0] == 0
        result = ContabilidadService.contabilizar_compra(cur,user,invoice,50,0,50,referencia=marker,fecha=datetime(2026,10,20,12))
    assert tuple(cur.execute('SELECT SUM(Debe),SUM(Haber) FROM contabilidad.DetalleAsientos WHERE AsientoID=?',result['asiento_id']).fetchone()) == (50,50)


def test_native_saldo_attributes_receiver_and_count_not_invoice_shift(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    cur.execute("UPDATE ventas.Facturas SET FechaHora='2026-10-19T12:00:00' WHERE ID=?",invoice)
    with as_db_role(cur,'Estandar'):
        cur.execute('EXEC ventas.sp_InsertarPagoFactura ?,?,?,?,?',invoice,'Efectivo',20,marker,None)
    cur.execute('UPDATE ventas.TurnosCaja SET Cerrado=1 WHERE ID=?', shift)
    receiver = cur.execute("INSERT INTO ventas.TurnosCaja(UsuarioID,FechaApertura,Cerrado) OUTPUT INSERTED.ID VALUES(?,GETDATE(),0)", user).fetchone()[0]
    with as_db_role(cur, 'Estandar'):
        cur.execute('EXEC ventas.sp_InsertarPagoSaldoEncargo ?,?,?,?,?,?,?,?', invoice,'Efectivo',30,marker,datetime(2026,10,20,12),None,receiver,user)
    movements=cur.execute('SELECT TurnoReceptorID,UsuarioReceptorID,FechaPago FROM ventas.Pagos WHERE FacturaID=? ORDER BY ID',invoice).fetchall()
    assert [(r[0],r[1],r[2].date().isoformat()) for r in movements] == [(shift,user,'2026-10-19'),(receiver,user,'2026-10-20')]
    cur.execute('EXEC ventas.sp_CalcularValoresSistemaTurno ?',receiver)
    assert cur.fetchone()[0] == 30
    cur.execute('EXEC ventas.sp_CalcularValoresSistemaTurno ?',shift)
    assert cur.fetchone()[0] == 20


def test_native_operativo_must_wait_for_cashier_then_deliver_prepaid(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    with as_db_role(cur,'Operativo'):
        with pytest.raises(pyodbc.Error,match='51032'):
            cur.execute('EXEC produccion.sp_ActualizarEstadoEncargoCompare ?,?,?','Entregado',marker[-10:],'Listo')
    assert cur.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?',invoice).fetchone()[0] == 'Listo'
    with as_db_role(cur,'Estandar'):
        cur.execute('EXEC ventas.sp_InsertarPagoFactura ?,?,?,?,?',invoice,'Efectivo',50,marker,None)
    with as_db_role(cur,'Operativo'):
        cur.execute('EXEC produccion.sp_ActualizarEstadoEncargoCompare ?,?,?','Entregado',marker[-10:],'Listo')
    assert cur.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?',invoice).fetchone()[0] == 'Entregado'


def test_native_historical_receiver_requires_evidence_and_admin(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    payment = cur.execute("INSERT INTO ventas.Pagos(FacturaID,MetodoPago,Monto) OUTPUT INSERTED.ID VALUES(?,'Efectivo',50)",invoice).fetchone()[0]
    with pytest.raises(pyodbc.Error,match='históricos'):
        cur.execute('EXEC ventas.sp_CalcularValoresSistemaTurno ?',shift).fetchone()
    with as_db_role(cur,'Estandar'):
        with pytest.raises(pyodbc.Error):
            cur.execute('EXEC ventas.sp_ConciliarReceptorPagoHistorico ?,?,?,?,?',payment,shift,user,user,marker)
    with as_db_role(cur,'Admin'):
        cur.execute('EXEC ventas.sp_ConciliarReceptorPagoHistorico ?,?,?,?,?',payment,shift,user,user,'Recibo firmado '+marker)
    assert tuple(cur.execute('SELECT TurnoReceptorID,UsuarioReceptorID FROM ventas.Pagos WHERE ID=?',payment).fetchone()) == (shift,user)
    cur.execute('EXEC ventas.sp_CalcularValoresSistemaTurno ?',shift)
    assert cur.fetchone()[0] == 50
    assert cur.execute("SELECT COUNT(*) FROM fiscal.BitacoraFiscal WHERE Accion='CONCILIAR_RECEPTOR_PAGO' AND EntidadID=?",payment).fetchone()[0] == 1


@pytest.mark.parametrize('role',['Estandar','Operativo'])
def test_native_route_voided_invoice_has_no_delivery_or_collection(sql_cash,monkeypatch,role):
    conn, cur, user, shift, invoice, marker = sql_cash
    cur.execute("UPDATE ventas.Facturas SET EstadoFiscal='Anulada' WHERE ID=?",invoice)
    client=delivery_client(monkeypatch,conn,user,role)
    with as_db_role(cur,role):
        response=client.put('/deliver/'+marker[-10:],json={'estado':'Entregado'})
    assert response.status_code == 409,response.json
    assert cur.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?',invoice).fetchone()[0] == 'Listo'
    assert cur.execute('SELECT COUNT(*) FROM ventas.Pagos WHERE FacturaID=?',invoice).fetchone()[0] == 0


def test_native_route_cashier_delivery_collects_once_with_real_journal(sql_cash,monkeypatch):
    conn, cur, user, shift, invoice, marker = sql_cash
    client=delivery_client(monkeypatch,conn,user,'Estandar')
    with as_db_role(cur,'Estandar'):
        first=client.put('/deliver/'+marker[-10:],json={'estado':'Entregado'})
        retry=client.put('/deliver/'+marker[-10:],json={'estado':'Entregado'})
    assert first.status_code == 200,first.json
    assert retry.status_code == 200,retry.json
    assert cur.execute('SELECT COUNT(*) FROM ventas.Pagos WHERE FacturaID=?',invoice).fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM contabilidad.AsientosDiario WHERE ReferenciaExterna=?",'SALDO-'+marker).fetchone()[0] == 1


def test_native_route_operativo_balance_is_rejected_before_change(sql_cash,monkeypatch):
    conn, cur, user, shift, invoice, marker = sql_cash
    client=delivery_client(monkeypatch,conn,user,'Operativo')
    with as_db_role(cur,'Operativo'):
        response=client.put('/deliver/'+marker[-10:],json={'estado':'Entregado'})
    assert response.status_code == 409,response.json
    assert 'cajero' in response.json['error']
    assert cur.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?',invoice).fetchone()[0] == 'Listo'
    assert cur.execute('SELECT COUNT(*) FROM ventas.Pagos WHERE FacturaID=?',invoice).fetchone()[0] == 0


def test_native_saldo_cannot_use_closed_receiving_shift(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    cur.execute('UPDATE ventas.TurnosCaja SET Cerrado=1 WHERE ID=?',shift)
    with as_db_role(cur,'Estandar'):
        with pytest.raises(pyodbc.Error,match='51026'):
            cur.execute('EXEC ventas.sp_InsertarPagoSaldoEncargo ?,?,?,?,?,?,?,?',invoice,'Efectivo',50,marker,datetime(2026,10,20,12),None,shift,user)
    assert cur.execute('SELECT COUNT(*) FROM ventas.Pagos WHERE FacturaID=?',invoice).fetchone()[0] == 0


def test_native_cashier_invoice_emission_audit_keeps_fiscal_deny(sql_cash):
    from app.services.fiscal_service import audit
    conn, cur, user, shift, invoice, marker = sql_cash
    with as_db_role(cur,'Estandar'):
        assert cur.execute("SELECT HAS_PERMS_BY_NAME('fiscal.sp_RegistrarBitacoraFiscal','OBJECT','EXECUTE')").fetchone()[0] == 0
        audit(cur,user,'EMISION','Factura',invoice,{'numero':marker,'total':50},'127.0.0.1')
    assert cur.execute("SELECT COUNT(*) FROM fiscal.BitacoraFiscal WHERE Accion='EMISION' AND EntidadID=?",invoice).fetchone()[0] == 1


def test_native_route_operativo_prepaid_delivery_is_audited(sql_cash,monkeypatch):
    conn, cur, user, shift, invoice, marker = sql_cash
    with as_db_role(cur,'Estandar'):
        cur.execute('EXEC ventas.sp_InsertarPagoFactura ?,?,?,?,?',invoice,'Efectivo',50,marker,None)
    client=delivery_client(monkeypatch,conn,user,'Operativo')
    with as_db_role(cur,'Operativo'):
        response=client.put('/deliver/'+marker[-10:],json={'estado':'Entregado'})
    assert response.status_code == 200,response.json
    assert cur.execute("SELECT COUNT(*) FROM fiscal.BitacoraFiscal WHERE Accion='ESTADO_ENCARGO' AND EntidadID=?",invoice).fetchone()[0] == 1


def test_native_unknown_legacy_saldo_blocks_potential_receiving_shift(sql_cash):
    conn, cur, user, shift, invoice, marker = sql_cash
    cur.execute("INSERT INTO ventas.Pagos(FacturaID,MetodoPago,Monto) VALUES(?,'Efectivo',50)",invoice)
    receiver=cur.execute("INSERT INTO ventas.TurnosCaja(UsuarioID,FechaApertura,Cerrado) OUTPUT INSERTED.ID VALUES(?,DATEADD(minute,-1,GETDATE()),0)",user).fetchone()[0]
    with pytest.raises(pyodbc.Error,match='51021'):
        cur.execute('EXEC ventas.sp_CalcularValoresSistemaTurno ?',receiver).fetchone()
