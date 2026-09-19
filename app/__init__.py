# app/__init__.py
# Application Factory — Punto central de configuración de Flask

from flask import Flask
from config import Config


def create_app(config_class=Config):
    """Crea y configura la instancia de la aplicación Flask."""

    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )
    app.config.from_object(config_class)

    # Inicializar extensiones
    from app.extensions import login_manager, csrf
    login_manager.init_app(app)
    csrf.init_app(app)

    # Importar modelos para registrar el user_loader
    from app import models  # noqa: F401

    # Registrar Blueprints
    from app.auth import auth_bp
    from app.hub import hub_bp
    from app.pos import pos_bp
    from app.monitor import monitor_bp
    from app.admin import admin_bp
    from app.kiosco import kiosco_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(hub_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(kiosco_bp)

    return app
