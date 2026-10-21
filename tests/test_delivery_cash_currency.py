"""Delivery and cash-count routes execute their actual SQL against synthetic rows.

The adapter translates SQL Server syntax only; it does not precompute sums.
"""
from datetime import date, datetime
from decimal import Decimal
from inspect import unwrap
import re
import sqlite3

import pytest
from flask import Flask

from app.admin import routes_pos
from app.monitor import routes as monitor
from app.services.contabilidad_service import ContabilidadService


class Row:
    def __init__(self, row):
        self.row = row

    def __getattr__(self, key):
        return self.row[key]

    def __getitem__(self, key):
        return self.row[key]


class DeliveryCashDB:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE Facturas(ID INTEGER PRIMARY KEY, NumeroFactura TEXT,
                CodigoSeguimiento TEXT, Total NUMERIC, TurnoID INT, EstadoFiscal TEXT);
            INSERT INTO Facturas VALUES(90001,'SYNTHETIC','SYNTHETIC',50,7,'Emitida');
            CREATE TABLE Encargos(FacturaID INT, Estado TEXT);
            INSERT INTO Encargos VALUES(90001,'Listo');
            CREATE TABLE Pagos(ID INTEGER PRIMARY KEY, FacturaID INT, MetodoPago TEXT,
                Monto NUMERIC, NombreTransferente TEXT, FechaPago TEXT,
                MonedaRegistro TEXT NOT NULL DEFAULT 'Legacy', TipoCambioAplicado NUMERIC,
                TurnoReceptorID INT, UsuarioReceptorID INT);
            CREATE TABLE TurnosCaja(ID INTEGER PRIMARY KEY, UsuarioID INT, Cerrado INT);
            INSERT INTO TurnosCaja VALUES(7,123,0);
            CREATE TABLE ConfiguracionSistema(Clave TEXT,Valor TEXT);
            INSERT INTO ConfiguracionSistema VALUES('tipo_cambio_usd','36.6243');
            INSERT INTO ConfiguracionSistema VALUES('umbral_discrepancia_cordobas','50');
            CREATE TABLE BitacoraFiscal(UsuarioID INT,Accion TEXT,Entidad TEXT,EntidadID INT,Detalle TEXT,IP TEXT);
            CREATE TABLE ArqueoCaja(ID INTEGER PRIMARY KEY,TurnoID INT,UsuarioID INT,
                EfectivoContado NUMERIC,TransferenciasContadas NUMERIC,DolaresContados NUMERIC,
                TipoCambioUsado NUMERIC,EfectivoSistema NUMERIC,TransferenciasSistema NUMERIC,
                DiferenciaEfectivo NUMERIC,DiferenciaTransferencias NUMERIC,Observaciones TEXT,
                EstadoArqueo TEXT,RequiereJustificacion INT);
            CREATE TABLE ArqueoAuditLog(ArqueoID INT,UsuarioID INT,Accion TEXT,Detalle TEXT,DireccionIP TEXT);
        ''')

    def cursor(self):
        return self

    def execute(self, sql, *args):
        sql = re.sub(r'WITH\s*\(UPDLOCK,\s*HOLDLOCK\)', '', sql, flags=re.I)
        sql = sql.replace('ISNULL(', 'IFNULL(')
        if 'UPDATE e SET Estado' in sql:
            sql = ('UPDATE Encargos SET Estado=? WHERE FacturaID IN '
                   "(SELECT ID FROM Facturas WHERE CodigoSeguimiento=? AND EstadoFiscal='Emitida') AND Estado=?")
        if 'OUTPUT INSERTED.ID' in sql:
            sql = sql.replace('OUTPUT INSERTED.ID', '') + ' RETURNING ID'
        values = tuple(str(value) if isinstance(value, Decimal) else value.isoformat()
                       if isinstance(value, (datetime, date)) else value for value in args)
        self.result = self.db.execute(sql, values)
        self.rowcount = self.result.rowcount
        return self

    def fetchone(self):
        result = self.result.fetchone()
        return Row(result) if result is not None else None

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        # Physical close belongs to the fixture; both routes share synthetic data.
        pass


@pytest.fixture
def delivery_cash(monkeypatch):
    from types import SimpleNamespace
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.add_url_rule('/deliver/<codigo>', view_func=unwrap(monitor.actualizar_estado), methods=['PUT'])
    app.add_url_rule('/count', view_func=unwrap(routes_pos.arqueo_etapa1_conteo), methods=['POST'])
    db = DeliveryCashDB()
    actor = SimpleNamespace(id=123)
    monkeypatch.setattr(monitor, 'get_db_connection', lambda: db)
    monkeypatch.setattr(routes_pos, 'get_db_connection', lambda: db)
    monkeypatch.setattr(monitor, 'current_user', actor)
    monkeypatch.setattr(routes_pos, 'current_user', actor)
    ledger = []
    def save_journal(cls, **kwargs):
        ledger.extend(kwargs['detalles'])
        return {'asiento_id': 99}
    monkeypatch.setattr(ContabilidadService, 'crear_asiento', classmethod(save_journal))
    try:
        yield app.test_client(), db, ledger
    finally:
        db.db.close()


def test_delivery_usd_balance_remains_national_currency_in_cash_count(delivery_cash):
    client, db, ledger = delivery_cash
    delivery = client.put('/deliver/SYNTHETIC', json={'estado': 'Entregado', 'metodo_pago': 'Efectivo USD'})
    assert delivery.status_code == 200, delivery.json
    assert ledger[0][1] == Decimal('50.00')
    count = client.post('/count', json={'efectivo_contado': 50, 'dolares_contados': 0, 'transferencias_contadas': 0})
    assert count.status_code == 200, count.json
    assert count.json['arqueo']['efectivo_sistema'] == 50
    assert count.json['arqueo']['diferencia_efectivo'] == 0
    payment = db.db.execute('SELECT Monto,MonedaRegistro,TipoCambioAplicado FROM Pagos').fetchone()
    assert payment['Monto'] == 50
    assert payment['MonedaRegistro'] == 'NIO'
    assert Decimal(str(payment['TipoCambioAplicado'])) == Decimal('36.6243')


def test_voided_delivery_has_no_payment_or_journal(delivery_cash):
    client, db, ledger = delivery_cash
    db.db.execute("UPDATE Facturas SET EstadoFiscal='Anulada'")
    db.db.commit()
    response = client.put('/deliver/SYNTHETIC', json={'estado':'Entregado'})
    assert response.status_code == 409
    assert db.db.execute('SELECT Estado FROM Encargos').fetchone()[0] == 'Listo'
    assert db.db.execute('SELECT COUNT(*) FROM Pagos').fetchone()[0] == 0
    assert ledger == []


def test_delivery_receives_balance_in_new_shift(delivery_cash):
    client, db, ledger = delivery_cash
    db.db.execute('UPDATE TurnosCaja SET Cerrado=1 WHERE ID=7')
    db.db.execute('INSERT INTO TurnosCaja VALUES(8,123,0)')
    db.db.commit()
    response = client.put('/deliver/SYNTHETIC', json={'estado':'Entregado'})
    assert response.status_code == 200, response.json
    assert tuple(db.db.execute('SELECT TurnoReceptorID,UsuarioReceptorID FROM Pagos').fetchone()) == (8,123)
    count = client.post('/count', json={'efectivo_contado':50})
    assert count.status_code == 200, count.json
    assert count.json['arqueo']['efectivo_sistema'] == 50


def test_delivery_without_receiver_open_shift_rolls_back(delivery_cash):
    client, db, ledger = delivery_cash
    db.db.execute('UPDATE TurnosCaja SET Cerrado=1')
    db.db.commit()
    response = client.put('/deliver/SYNTHETIC', json={'estado':'Entregado'})
    assert response.status_code == 409
    assert db.db.execute('SELECT Estado FROM Encargos').fetchone()[0] == 'Listo'
    assert db.db.execute('SELECT COUNT(*) FROM Pagos').fetchone()[0] == 0
    assert ledger == []


def test_repeated_delivery_does_not_receive_balance_twice(delivery_cash):
    client, db, ledger = delivery_cash
    assert client.put('/deliver/SYNTHETIC',json={'estado':'Entregado'}).status_code == 200
    assert client.put('/deliver/SYNTHETIC',json={'estado':'Entregado'}).status_code == 200
    assert db.db.execute('SELECT COUNT(*) FROM Pagos').fetchone()[0] == 1
    assert len(ledger) == 2
