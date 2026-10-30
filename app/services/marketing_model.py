"""Modelos locales, pequeños y explicables para productos y ventas.

La instantánea no contiene identificadores de clientes. El historial propio se
aplica solo al calcular recomendaciones para la sesión autenticada.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from math import exp, isfinite, log1p


MODEL_VERSION = 1
WINDOW_DAYS = 180
PAIR_LIMIT = 20


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def train_model(rows, now=None):
    """Entrena popularidad con decaimiento y afinidad por cesta sin PII."""
    trained_at = now or datetime.now()
    today = _day(trained_at)
    products = defaultdict(lambda: {'units_30': 0, 'units_prior_30': 0,
                                    'units_180': 0, 'revenue_30': 0.0,
                                    'revenue_prior_30': 0.0, 'score': 0.0})
    baskets = defaultdict(set)
    invoice_days = {}
    invoice_revenue = defaultdict(float)
    daily_revenue = defaultdict(float)
    source_rows = 0

    for row in rows:
        if row.get('status', 'Emitida') != 'Emitida':
            continue
        try:
            invoice_id = int(row['invoice_id'])
            product_id = int(row['product_id'])
            qty = int(row['quantity'])
            revenue = float(row['revenue'])
            sold_day = _day(row['sold_at'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        age = (today - sold_day).days
        if invoice_id <= 0 or product_id <= 0 or qty <= 0 or not isfinite(revenue) or revenue < 0 or not 0 <= age < WINDOW_DAYS:
            continue

        source_rows += 1
        key = str(product_id)
        metrics = products[key]
        metrics['units_180'] += qty
        metrics['score'] += log1p(qty) * exp(-age / 30.0)
        if age < 30:
            metrics['units_30'] += qty
            metrics['revenue_30'] += revenue
        elif age < 60:
            metrics['units_prior_30'] += qty
            metrics['revenue_prior_30'] += revenue
        baskets[invoice_id].add(key)
        invoice_days[invoice_id] = sold_day
        invoice_revenue[invoice_id] += revenue
        if age < 60:
            daily_revenue[sold_day] += revenue

    pairs = defaultdict(Counter)
    for product_set in baskets.values():
        product_ids = sorted(product_set, key=int)[:50]
        for index, left in enumerate(product_ids):
            for right in product_ids[index + 1:]:
                pairs[left][right] += 1
                pairs[right][left] += 1

    output_pairs = {}
    for product_id, neighbors in pairs.items():
        output_pairs[product_id] = dict(sorted(neighbors.items(),
                                                key=lambda pair: (-pair[1], int(pair[0])))[:PAIR_LIMIT])

    for metrics in products.values():
        metrics['score'] = round(metrics['score'], 6)
        metrics['revenue_30'] = round(metrics['revenue_30'], 2)
        metrics['revenue_prior_30'] = round(metrics['revenue_prior_30'], 2)

    recent_invoices = sum(0 <= (today - day).days < 30 for day in invoice_days.values())
    prior_invoices = sum(30 <= (today - day).days < 60 for day in invoice_days.values())
    return {
        'version': MODEL_VERSION,
        'trained_at': trained_at.isoformat() if isinstance(trained_at, datetime)
                      else datetime.combine(today, datetime.min.time()).isoformat(),
        'window_days': WINDOW_DAYS,
        'source_rows': source_rows,
        'invoice_count': len(baskets),
        'recent_invoices': recent_invoices,
        'prior_invoices': prior_invoices,
        'revenue_30': round(sum(amount for invoice, amount in invoice_revenue.items()
                                if 0 <= (today - invoice_days[invoice]).days < 30), 2),
        'revenue_prior_30': round(sum(amount for invoice, amount in invoice_revenue.items()
                                      if 30 <= (today - invoice_days[invoice]).days < 60), 2),
        'products': dict(products),
        'pairs': output_pairs,
        'daily': [{'day': (today - timedelta(days=offset)).isoformat(),
                   'revenue': round(daily_revenue[today - timedelta(days=offset)], 2)}
                  for offset in range(59, -1, -1)],
    }


def recommend_products(model, catalog, history=None, limit=6, cart=None):
    """Ordena productos activos usando la instantánea y solo el historial propio."""
    model = model or {}
    metrics = model.get('products') or {}
    pairs = model.get('pairs') or {}
    history = {str(key): max(0, int(value)) for key, value in (history or {}).items()}
    cart = {str(key) for key in (cart or ())}
    names = {str(item['id']): item.get('nombre', '') for item in catalog}
    candidates = []
    for item in catalog:
        key = str(item['id'])
        if not item.get('activo', True) or item.get('es_ficticio') or key in cart:
            continue
        own = metrics.get(key, {})
        score = float(own.get('score', 0))
        cart_links = sorted(((int(pairs.get(source, {}).get(key, 0)), source)
                             for source in cart), reverse=True)
        history_links = sorted(((int(pairs.get(source, {}).get(key, 0)), source)
                                for source, qty in history.items() if qty > 0), reverse=True)
        if cart_links and cart_links[0][0] > 0:
            score += cart_links[0][0] * 3.0
            reason = f"Se compra junto con {names.get(cart_links[0][1], 'tu pedido')}"
        elif history_links and history_links[0][0] > 0:
            score += history_links[0][0] * 3.0
            reason = f"Se compra junto con {names.get(history_links[0][1], 'tus favoritos')}"
        elif history.get(key, 0) > 0:
            score += min(history[key], 10) * 0.4
            reason = 'Uno de tus favoritos'
        elif float(item.get('descuento') or 0) > 0:
            reason = 'Promoción vigente'
        else:
            reason = 'Popular en la tienda' if score > 0 else 'Descubre algo nuevo'
        discount = max(0.0, min(100.0, float(item.get('descuento') or 0)))
        score += discount / 100.0
        candidates.append((score, discount, int(item['id']), {**item, 'motivo': reason}))
    candidates.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
    return [entry[3] for entry in candidates[:max(0, int(limit))]]


def business_insights(model, catalog):
    """Propone experimentos con evidencia, sin atribuir causas ni rentabilidad."""
    model = model or {}
    if not model.get('source_rows'):
        return [{'tipo': 'datos', 'titulo': 'Aún faltan ventas para aprender',
                 'evidencia': 'No hay facturas emitidas en la ventana de entrenamiento.',
                 'accion': 'Registra ventas reales y vuelve a entrenar el modelo.'}]
    active = {str(item['id']): item for item in catalog
              if item.get('activo', True) and not item.get('es_ficticio')}
    insights = []
    seen_pairs = set()
    for left, neighbors in (model.get('pairs') or {}).items():
        for right, count in neighbors.items():
            pair = tuple(sorted((left, right), key=int))
            if pair in seen_pairs or count < 3 or left not in active or right not in active:
                continue
            seen_pairs.add(pair)
            insights.append({
                'tipo': 'combo',
                'titulo': f"Probar combo: {active[pair[0]]['nombre']} + {active[pair[1]]['nombre']}",
                'evidencia': f'Estos productos aparecieron juntos en {count} facturas emitidas.',
                'accion': 'Prueba mostrarlos juntos y mide si crece la venta conjunta; fija cualquier descuento en Catálogo.',
                'fuerza': count,
            })
    if (not model.get('sample_truncated')
            and model.get('recent_invoices', 0) >= 5
            and model.get('prior_invoices', 0) >= 5):
        for key, metrics in (model.get('products') or {}).items():
            if key not in active:
                continue
            current = int(metrics.get('units_30', 0))
            previous = int(metrics.get('units_prior_30', 0))
            if current < 5 or previous < 5:
                continue
            change = (current - previous) / previous
            if change >= 0.3:
                action = 'Revisa capacidad de producción y prueba una presentación destacada.'
                title = f"Más interés en {active[key]['nombre']}"
            elif change <= -0.3:
                action = 'Revisa disponibilidad, visibilidad y precio antes de decidir una promoción.'
                title = f"Revisar {active[key]['nombre']}"
            else:
                continue
            insights.append({'tipo': 'tendencia', 'titulo': title,
                             'evidencia': f'{previous} unidades en los 30 días anteriores; {current} en los últimos 30 días.',
                             'accion': action, 'fuerza': abs(current - previous)})
    insights.sort(key=lambda item: (-item.get('fuerza', 0), item['titulo']))
    for insight in insights:
        insight.pop('fuerza', None)
    if model.get('sample_truncated'):
        insights.insert(0, {
            'tipo': 'datos',
            'titulo': 'Análisis con muestra parcial',
            'evidencia': 'Se analizaron los 30 000 renglones de venta más recientes; algunas ventas del período pueden faltar.',
            'accion': 'Compara estas señales con los reportes completos antes de decidir cambios de producción o precios.',
        })
    if not insights:
        insights.append({'tipo': 'datos', 'titulo': 'Observar antes de cambiar',
                         'evidencia': f"{model.get('invoice_count', 0)} facturas útiles en 180 días; todavía no hay señales fuertes.",
                         'accion': 'Mantén el registro de ventas y revisa de nuevo cuando haya más compras.'})
    return insights[:8]
