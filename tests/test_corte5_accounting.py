"""Un anticipo se explica en el libro mayor sin cambiar su asiento."""
from decimal import Decimal

from app.services.contabilidad_service import ContabilidadService


class Cursor:
    def fetchone(self):
        return (1,)


def test_advance_entries_show_received_share_and_the_receivable(monkeypatch):
    monkeypatch.setattr(
        ContabilidadService, 'crear_asiento',
        classmethod(lambda cls, **values: values),
    )
    monkeypatch.setattr('app.services.contabilidad_service.execute_sp', lambda *args, **kwargs: Cursor())
    entry = ContabilidadService.contabilizar_venta(
        Cursor(), 1, 'FAC-00000030', Decimal('100.00'), Decimal('0'),
        Decimal('100.00'), [{'metodo': 'Efectivo', 'monto': Decimal('50.00')}],
        es_encargo=True, adelanto=Decimal('50.00'),
    )
    advance, receivable = entry['detalles'][:2]
    assert advance[0] == '1.1.01.001'
    assert advance[1] == Decimal('50.00')
    assert 'FAC-00000030 (50%)' in advance[3]
    assert 'Recibido en Caja' in advance[3]
    assert receivable[0] == ContabilidadService.ENCARGOS_POR_COBRAR
    assert receivable[1] == Decimal('50.00')


def test_balance_payment_is_named_as_delivery_collection(monkeypatch):
    monkeypatch.setattr(
        ContabilidadService, 'crear_asiento',
        classmethod(lambda cls, **values: values),
    )
    entry = ContabilidadService.contabilizar_cobro_encargo(
        Cursor(), 1, 'FAC-00000030', Decimal('50.00'), metodo_pago='Efectivo',
    )
    debit, credit = entry['detalles']
    assert debit[0] == '1.1.01.001' and debit[1] == Decimal('50.00')
    assert 'Liquidación Saldo Encargo FAC-00000030' in debit[3]
    assert 'Entrega de Producto' in debit[3]
    assert credit[0] == ContabilidadService.ENCARGOS_POR_COBRAR
    assert credit[2] == Decimal('50.00')


def test_usd_cash_advance_is_not_labeled_as_bank(monkeypatch):
    monkeypatch.setattr(
        ContabilidadService, 'crear_asiento',
        classmethod(lambda cls, **values: values),
    )
    monkeypatch.setattr('app.services.contabilidad_service.execute_sp', lambda *args, **kwargs: Cursor())
    entry = ContabilidadService.contabilizar_venta(
        Cursor(), 1, 'FAC-00000031', Decimal('100.00'), 0, Decimal('100.00'),
        [{'metodo': 'Efectivo USD', 'monto': Decimal('50.00')}],
        es_encargo=True, adelanto=Decimal('50.00'),
    )
    assert entry['detalles'][0][0] == ContabilidadService.CAJA_GENERAL_USD
    assert 'Recibido en Caja' in entry['detalles'][0][3]
