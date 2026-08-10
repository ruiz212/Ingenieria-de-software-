# app/auth/routes.py
# Rutas de autenticación: Login y Logout

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from app.auth import auth_bp
from app.models import User


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pantalla de inicio de sesión."""
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user, password_hash = User.get_by_username(username)

        if user and check_password_hash(password_hash, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('hub.main_hub'))
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario activo."""
    logout_user()
    return redirect(url_for('auth.login'))
