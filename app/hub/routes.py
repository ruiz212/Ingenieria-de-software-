# app/hub/routes.py
# Ruta del Hub Principal del sistema

from flask import redirect, url_for
from flask_login import login_required, current_user

from app.hub import hub_bp


@hub_bp.route('/')
@login_required
def main_hub():
    """Redirige al módulo correspondiente según el rol del usuario."""
    rol = current_user.rol_nombre
    
    if rol in ['SuperAdmin', 'Admin']:
        return redirect(url_for('admin.dashboard'))
    elif rol == 'Estandar':
        return redirect(url_for('pos.index'))
    elif rol == 'Invitado':
        return redirect(url_for('monitor.monitor_pedidos'))
    
    # Fallback por si acaso
    return redirect(url_for('pos.index'))
