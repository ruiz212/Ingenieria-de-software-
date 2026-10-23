"""Vencimiento por inactividad real y renovación explícita de la sesión."""
from datetime import timedelta
from time import time

from flask import jsonify, redirect, request, session, url_for
from flask_login import logout_user, user_logged_in


SESSION_ACTIVITY_KEY = 'last_user_action_at'


def lifetime_seconds(app):
    lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    return int(lifetime.total_seconds() if isinstance(lifetime, timedelta) else lifetime)


def renew_session():
    session.permanent = True
    session[SESSION_ACTIVITY_KEY] = int(time())


def install_session_guard(app):
    @user_logged_in.connect_via(app)
    def start_logged_in_session(sender, user, **kwargs):
        renew_session()

    @app.before_request
    def expire_inactive_session():
        if not session.get('_user_id'):
            # Cookies "remember" de versiones previas no deben reconstruir una sesión sin reloj.
            remember_name = app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')
            if request.cookies.get(remember_name):
                logout_user()
                session.clear()
                if request.path == '/auth/ping' or '/api/' in request.path or request.is_json:
                    return jsonify(error='La sesión venció. Inicia sesión de nuevo.'), 401
            return None
        now = int(time())
        last = session.get(SESSION_ACTIVITY_KEY)
        if last is None:
            # Sesiones abiertas antes de instalar este control conservan su acceso.
            renew_session()
            return None
        try:
            expired = now - int(last) >= lifetime_seconds(app)
        except (TypeError, ValueError):
            expired = True
        if not expired:
            return None
        logout_user()
        session.clear()
        if request.path == '/auth/ping' or '/api/' in request.path or request.is_json:
            return jsonify(error='La sesión venció por inactividad. Inicia sesión de nuevo.'), 401
        return redirect(url_for('auth.login'))
