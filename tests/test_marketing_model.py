"""El modelo local usa ventas reales sin conservar identidades personales."""

import json
from datetime import datetime, timedelta

from app.services.marketing_model import business_insights, recommend_products, train_model


NOW = datetime(2026, 10, 26, 12, 0)


def sale(invoice, product, days_ago, *, qty=1, revenue=50, status='Emitida', customer=9):
    return {
        'invoice_id': invoice,
        'product_id': product,
        'sold_at': NOW - timedelta(days=days_ago),
        'quantity': qty,
        'revenue': revenue,
        'status': status,
        'customer_id': customer,
    }


def catalog(*ids):
    return [dict(id=pid, nombre=f'Producto {pid}', categoria='Pan', precio=50,
                 descuento=0, activo=True, es_ficticio=False) for pid in ids]


def test_training_excludes_cancelled_and_old_sales_and_personal_data():
    model = train_model([
        sale(1, 1, 2, qty=3), sale(1, 2, 2),
        sale(2, 1, 45), sale(3, 3, 1, status='Anulada'),
        sale(4, 4, 190),
    ], NOW)

    assert model['source_rows'] == 3
    assert model['trained_at'] == '2026-10-26T12:00:00'
    assert model['invoice_count'] == 2
    assert model['products']['1']['units_30'] == 3
    assert model['products']['1']['units_prior_30'] == 1
    assert model['pairs']['1']['2'] == 1
    assert '3' not in model['products'] and '4' not in model['products']
    assert 'customer_id' not in json.dumps(model)
    assert 'customer' not in json.dumps(model)


def test_recommendations_use_own_favorites_and_basket_pairs_without_guest_identity():
    rows = [sale(1, 1, 1), sale(1, 2, 1), sale(2, 1, 2), sale(2, 2, 2),
            sale(3, 3, 1, qty=10)]
    model = train_model(rows, NOW)
    products = catalog(1, 2, 3, 4)
    products[2]['activo'] = False
    products[3]['es_ficticio'] = True

    guest = recommend_products(model, products, {}, limit=3)
    personal = recommend_products(model, products, {1: 4}, limit=3)

    assert [item['id'] for item in guest] == [1, 2]
    assert personal[0]['id'] == 2
    assert 'junto' in personal[0]['motivo'].lower()


def test_business_insights_require_evidence_and_explain_a_combo():
    small = train_model([sale(1, 1, 1)], NOW)
    assert not any(item['tipo'] == 'tendencia' for item in business_insights(small, catalog(1)))

    rows = []
    for invoice in range(1, 5):
        rows.extend([sale(invoice, 1, invoice), sale(invoice, 2, invoice)])
    model = train_model(rows, NOW)
    insights = business_insights(model, catalog(1, 2))

    combo = next(item for item in insights if item['tipo'] == 'combo')
    assert 'Producto 1' in combo['titulo'] and 'Producto 2' in combo['titulo']
    assert '4' in combo['evidencia']


def test_cart_recommendations_prioritize_products_bought_together():
    model = {
        'products': {'2': {'score': 1}, '3': {'score': 9}},
        'pairs': {'1': {'2': 4}},
    }

    result = recommend_products(model, catalog(1, 2, 3), cart={1}, limit=2)

    assert [item['id'] for item in result] == [2, 3]
    assert 'junto con Producto 1' in result[0]['motivo']


def test_truncated_sample_does_not_claim_product_growth():
    rows = [sale(invoice, 1, 2, qty=10) for invoice in range(1, 6)]
    rows += [sale(invoice, 1, 35, qty=5) for invoice in range(6, 11)]
    model = train_model(rows, NOW)
    model['sample_truncated'] = True

    insights = business_insights(model, catalog(1))

    assert not any(item['tipo'] == 'tendencia' for item in insights)
