"""Pruebas de reglas monetarias sin conexión a datos reales."""
from decimal import Decimal
import pytest
from app.services.validation import amount, positive_int
from app.services.fiscal_service import normalize_payments, calculate_sale
from app.services.contabilidad_service import ContabilidadService, ContabilidadError


@pytest.mark.parametrize('value',['NaN','Infinity','-1','abc',None,True])
def test_money_rejects_invalid_values(value):
    with pytest.raises(ValueError): amount(value)


def test_money_rounds_half_up():
    assert amount('0.105')==Decimal('0.11')


def test_fractional_quantity_rejected():
    with pytest.raises(ValueError): positive_int('1.5')


@pytest.mark.parametrize('lines',[
    [('a',-10,0),('b',0,-10)], [('a',10,10),('b',10,10)],
    [('a',0,0),('b',0,0)], [('a',10,0),('b',0,9)], [('a','NaN',0),('b',0,10)]])
def test_invalid_journal(lines):
    with pytest.raises((ContabilidadError,ValueError)): ContabilidadService._validar_partida_doble(lines)


def test_decimal_journal_balances():
    ContabilidadService._validar_partida_doble([('a',0.1+0.2,0),('b',0,0.3)])


def test_change_only_from_cash():
    payments,change=normalize_payments([{'metodo':'Efectivo','monto':100},{'metodo':'Transferencia','monto':50,'referencia':'ABC'}],Decimal('120'))
    assert change==30 and sum(p['monto'] for p in payments)==120
    assert payments[1]['monto']==50


@pytest.mark.parametrize('payments,total,advance',[
    ([{'metodo':'Transferencia','monto':150,'referencia':'ABC'}],100,None),
    ([{'metodo':'Efectivo','monto':10}],100,None),
    ([{'metodo':'Efectivo','monto':110}],100,110),
    ([{'metodo':'Tarjeta inventada','monto':100}],100,None)])
def test_invalid_payments(payments,total,advance):
    with pytest.raises(ValueError): normalize_payments(payments,Decimal(total),advance)


@pytest.mark.parametrize('total,advance', [('100', '0'), ('100', '49.99'), ('2.01', '1.00')])
def test_encargo_rejects_advance_below_half(total, advance):
    with pytest.raises(ValueError, match='50%'):
        normalize_payments([{'metodo': 'Efectivo', 'monto': advance}], Decimal(total), advance)


@pytest.mark.parametrize('total,advance', [('100', '50'), ('100', '75'), ('2.01', '1.01')])
def test_encargo_accepts_minimum_advance(total, advance):
    payments, change = normalize_payments(
        [{'metodo': 'Efectivo', 'monto': advance}], Decimal(total), advance
    )
    assert sum(p['monto'] for p in payments) == Decimal(advance)
    assert change == 0


class ProductCursor:
    def execute(self,*args): return self
    def fetchone(self): return ('Pan',Decimal('10'),Decimal('10'),Decimal('15'),None,False)


def test_server_ignores_forged_prices():
    cfg={k:'dato verificado' for k in ['fiscal_razon_social','fiscal_ruc','fiscal_direccion','fiscal_telefono','fiscal_autorizacion']}
    cfg['fiscal_regimen']='General'
    lines,subtotal,tax,total=calculate_sale(ProductCursor(),[{'id':1,'cantidad':2,'precio':0.01,'subtotal':0.02}],cfg)
    assert subtotal==18 and tax==Decimal('2.70') and total==Decimal('20.70')
    assert lines[0]['precio']==9


class CustomQuoteCursor:
    def __init__(self, quote_row=(42, 'Pastel de Chocolate 2 pisos', Decimal('450.00')), base_row=(99, Decimal('15'), None)):
        self.quote_row = quote_row
        self.base_row = base_row
        self.last_sql = ''

    def execute(self, sql, *args):
        self.last_sql = sql
        return self

    def fetchone(self):
        if 'FROM Cotizaciones' in self.last_sql:
            return self.quote_row
        if 'FROM Productos' in self.last_sql:
            return self.base_row
        return None


def test_calculate_sale_custom_quote_uses_server_price():
    cfg = {k: 'dato verificado' for k in ['fiscal_razon_social', 'fiscal_ruc', 'fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion']}
    cfg['fiscal_regimen'] = 'Cuota Fija'
    cursor = CustomQuoteCursor()
    lines, subtotal, tax, total = calculate_sale(
        cursor,
        [{'id': 'custom_42', 'cantidad': 1, 'precio': 1.00, 'nombre': 'Pastel Falsificado'}],
        cfg
    )
    assert len(lines) == 1
    assert lines[0]['id'] == 99
    assert lines[0]['cotizacion_id'] == 42
    assert lines[0]['precio'] == 450.0
    assert subtotal == Decimal('450.00')
    assert tax == Decimal('0.00')
    assert total == Decimal('450.00')


def test_calculate_sale_rejects_unpriced_custom_quote():
    cfg = {k: 'dato verificado' for k in ['fiscal_razon_social', 'fiscal_ruc', 'fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion']}
    cfg['fiscal_regimen'] = 'Cuota Fija'
    cursor = CustomQuoteCursor(quote_row=None)
    with pytest.raises(ValueError, match='no tiene precio autorizado'):
        calculate_sale(cursor, [{'id': 'custom_99', 'cantidad': 1}], cfg)


class DiscountWithExtrasCursor:
    def __init__(self):
        self.last_sql = ''

    def execute(self, sql, *args):
        self.last_sql = sql
        return self

    def fetchone(self):
        if 'FROM Ingredientes' in self.last_sql:
            return (5, 'Fresas', Decimal('25.00'))
        return ('Pastel Base', Decimal('199.99'), Decimal('15'), Decimal('0'), None, True)


def test_discount_rounds_base_before_adding_extras():
    cfg = {k: 'dato verificado' for k in ['fiscal_razon_social', 'fiscal_ruc', 'fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion']}
    cfg['fiscal_regimen'] = 'Cuota Fija'
    lines, subtotal, tax, total = calculate_sale(
        DiscountWithExtrasCursor(),
        [{
            'id': '10_12345',
            'cantidad': 1,
            'detalle_ingredientes': {'ingredientes': [{'nombre': 'Fresas'}]}
        }],
        cfg
    )
    # 199.99 * 0.85 = 169.9915 -> 169.99 + 25.00 = 194.99
    assert lines[0]['precio'] == 194.99
    assert total == Decimal('194.99')


def test_contabilizar_cobro_encargo_creates_balanced_entry(monkeypatch):
    recorded = {}

    def fake_crear_asiento(**kwargs):
        ContabilidadService._validar_partida_doble([(d[0], d[1], d[2]) for d in kwargs['detalles']])
        recorded.update(kwargs)
        return {'asiento_id': 777, 'numero_comprobante': 'CI-0001', 'periodo_id': 1}

    monkeypatch.setattr(ContabilidadService, 'crear_asiento', staticmethod(fake_crear_asiento))
    res = ContabilidadService.contabilizar_cobro_encargo(
        cursor=object(),
        usuario_id=1,
        numero_factura='FAC-000015',
        monto_saldo=Decimal('250.00'),
        metodo_pago='Transferencia'
    )
    assert res['asiento_id'] == 777
    assert recorded['tipo_comprobante'] == 'IN'
    assert recorded['referencia_externa'] == 'SALDO-FAC-000015'
    cuentas = [(d[0], d[1], d[2]) for d in recorded['detalles']]
    assert ('1.1.01.004', Decimal('250.00'), 0) in cuentas
    assert (ContabilidadService.ENCARGOS_POR_COBRAR, 0, Decimal('250.00')) in cuentas




