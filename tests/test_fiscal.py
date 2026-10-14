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
