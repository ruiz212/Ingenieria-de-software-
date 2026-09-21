# app/auth/decorators.py
# Decoradores para control de acceso por roles

from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def roles_required(*roles):
    """
    Decorador que verifica si el usuario actual tiene alguno de los roles permitidos.
    Si no tiene acceso, lo redirige al hub principal.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            if current_user.rol_nombre not in roles:
                flash(f"Acceso denegado: Se requiere rol {', '.join(roles)} para entrar aquí.", "error")
                return redirect(url_for('hub.main_hub'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
