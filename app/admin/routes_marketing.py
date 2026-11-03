"""Panel de mercadotecnia local, limitado a gerencia."""

from datetime import datetime, timedelta

from flask import current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.admin import admin_bp
from app.auth.decorators import roles_required
from app.db import get_db_connection
from app.services.business_time import business_now
from app.services.marketing_model import business_insights
from app.services.marketing_repository import (
    load_marketing_catalog,
    load_model,
    train_and_save,
)


def _needs_training(model, now):
    if not model:
        return True
    try:
        trained = datetime.fromisoformat(model['trained_at'])
        return trained > now or now - trained >= timedelta(hours=24)
    except (KeyError, TypeError, ValueError):
        return True


@admin_bp.route('/mercadotecnia')
@login_required
@roles_required('Admin', 'SuperAdmin')
def mercadotecnia():
    """Actualiza diariamente y presenta acciones que siempre citan su evidencia."""
    conn = get_db_connection()
    cursor = conn.cursor()
    model = None
    catalog = []
    error = None
    try:
        now = business_now()
        model = load_model(cursor)
        if _needs_training(model, now):
            model = train_and_save(cursor, now)
            conn.commit()
        catalog = load_marketing_catalog(cursor)
    except Exception:
        conn.rollback()
        current_app.logger.exception('No se pudo preparar el panel de mercadotecnia')
        error = 'El análisis no está disponible. Comprueba la migración de mercadotecnia y la conexión a la base de datos.'
    finally:
        conn.close()

    by_id = {str(item['id']): item for item in catalog}
    metrics = (model or {}).get('products') or {}
    top_products = [
        {**by_id[key], **values}
        for key, values in metrics.items() if key in by_id
    ]
    top_products.sort(key=lambda item: (-item['units_30'], -item['revenue_30'], item['nombre']))
    promotions = [item for item in catalog if item.get('descuento', 0) > 0]
    insights = business_insights(model, catalog)
    last_days = ((model or {}).get('daily') or [])[-14:]
    peak = max((float(day['revenue']) for day in last_days), default=0.0)
    daily_sales = last_days
    return render_template('admin/mercadotecnia.html', user=current_user,
                           modelo=model, productos_destacados=top_products[:8],
                           promociones=promotions, observaciones=insights,
                           ventas_diarias=daily_sales,
                           max_ventas_diarias=max(peak, 1), error_modelo=error)


@admin_bp.route('/mercadotecnia/entrenar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def entrenar_mercadotecnia():
    """Actualización manual con CSRF y roles; jamás altera precios o descuentos."""
    conn = get_db_connection()
    try:
        model = train_and_save(conn.cursor(), business_now())
        conn.commit()
        flash(f"Análisis actualizado con {model['source_rows']} renglones de ventas.", 'success')
    except Exception:
        conn.rollback()
        current_app.logger.exception('No se pudo entrenar mercadotecnia')
        flash('No se pudo actualizar el análisis. Revisa la migración y vuelve a intentar.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin.mercadotecnia'))
