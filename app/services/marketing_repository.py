"""Persistencia SQL del modelo local; los permisos viven en los procedimientos."""

import json
import logging
from datetime import datetime, timedelta

import pyodbc

from app.db import execute_sp
from app.services.marketing_model import WINDOW_DAYS, recommend_products, train_model


log = logging.getLogger(__name__)


def load_model(cursor, *, public=False):
    """Separa la vista comercial completa de la instantánea pública."""
    procedure = ('crm.sp_LeerModeloPublicoMercadotecnia' if public
                 else 'crm.sp_LeerModeloMercadotecnia')
    execute_sp(cursor, procedure)
    row = cursor.fetchone()
    if not row:
        return None
    raw = getattr(row, 'ModeloJSON', row[0] if isinstance(row, (list, tuple)) else None)
    model = json.loads(raw)
    return model if isinstance(model, dict) and model.get('version') == 1 else None


def customer_history(cursor):
    """El SP decide qué cliente es dueño de la sesión; no acepta IDs externos."""
    execute_sp(cursor, 'crm.sp_HistorialPersonalMercadotecnia')
    return {int(row.ProductoID): int(row.Unidades) for row in cursor.fetchall()
            if int(row.Unidades) > 0}


def load_marketing_catalog(cursor):
    """Usa la misma lista de productos activos que el punto de venta."""
    execute_sp(cursor, 'catalogo.sp_ObtenerProductosPOS')
    return [
        {'id': row.ID, 'nombre': row.Nombre, 'categoria': row.Categoria,
         'precio': float(row.PrecioBase), 'descuento': float(row.PorcentajeDescuento),
         'es_ficticio': bool(row.EsFicticio), 'activo': True,
         'imagen_url': row.ImagenUrl or ''}
        for row in cursor.fetchall()
    ]


def train_and_save(cursor, now=None):
    """Entrena de forma acotada y guarda una instantánea compartida por workers."""
    now = now or datetime.now()
    execute_sp(cursor, 'crm.sp_DatosEntrenamientoMercadotecnia',
               (now - timedelta(days=WINDOW_DAYS),))
    rows = [
        {'invoice_id': row.FacturaID, 'product_id': row.ProductoID,
         'quantity': row.Cantidad, 'revenue': row.Subtotal, 'sold_at': row.FechaHora}
        for row in cursor.fetchall()
    ]
    model = train_model(rows, now)
    model['sample_truncated'] = len(rows) >= 30000
    payload = json.dumps(model, ensure_ascii=False, separators=(',', ':'))
    public_model = {
        'version': model['version'],
        'trained_at': model['trained_at'],
        'products': {key: {'score': values['score']}
                     for key, values in model['products'].items()},
        'pairs': model['pairs'],
    }
    public_payload = json.dumps(public_model, ensure_ascii=False, separators=(',', ':'))
    execute_sp(cursor, 'crm.sp_GuardarModeloMercadotecnia',
               (payload, public_payload, model['source_rows']))
    return model


def store_recommendations(cursor, catalog, user, *, cart=None, limit=6):
    """Sirve sugerencias sin consultar nunca el historial de un invitado."""
    try:
        model = load_model(cursor, public=True)
    except (pyodbc.Error, ValueError, TypeError):
        log.warning('Modelo de mercadotecnia no disponible; se usa catálogo.', exc_info=True)
        model = None
    history = {}
    registered = (
        getattr(user, 'is_authenticated', False)
        and getattr(user, 'rol_nombre', None) == 'Cliente'
        and not getattr(user, 'es_invitado', False)
        and str(getattr(user, 'id', '')).isdigit()
        and int(user.id) > 1
    )
    if registered:
        try:
            history = customer_history(cursor)
        except pyodbc.Error:
            log.warning('Historial personal no disponible; se usan tendencias generales.', exc_info=True)
    return recommend_products(model, catalog, history, limit=limit, cart=cart)
