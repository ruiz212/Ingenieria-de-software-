# app/extensions.py
# Inicialización de extensiones de Flask (desacopladas de la app)

from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Por favor, inicie sesión para acceder a esta página."
login_manager.login_message_category = "warning"

csrf = CSRFProtect()
