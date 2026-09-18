# app/admin/__init__.py

from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

from app.admin import (
    routes_dashboard,
    routes_catalog,
    routes_users,
    routes_accounting,
    routes_inventory,
    routes_production,
    routes_pos,
    routes_hr,
    routes_fidelizacion
)  # noqa: E402, F401
