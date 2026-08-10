# app/hub/routes.py
# Ruta del Hub Principal del sistema

from flask import render_template
from flask_login import login_required, current_user

from app.hub import hub_bp


@hub_bp.route('/')
@login_required
def main_hub():
    """Pantalla Principal (Hub) del Sistema."""
    return render_template('main.html', user=current_user)
