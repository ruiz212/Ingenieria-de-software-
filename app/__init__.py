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
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    from app.assets import init_assets
    init_assets(app)

    # Configuración para producción (Azure App Service)
    from app.services.request_context import TrustedProxyFix
    from whitenoise import WhiteNoise
    
    # Forwarded headers are accepted only from the explicitly configured edge.
    app.wsgi_app = TrustedProxyFix(
        app.wsgi_app,
        trusted_cidrs=app.config.get('TRUSTED_PROXY_CIDRS', ()),
        forwarded_for_hops=app.config.get('PROXY_X_FOR_HOPS', 1),
    )
    
    # 2. Servir archivos estáticos eficientemente en producción y desarrollo
    import os
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../static')
    app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_path, prefix='static/', autorefresh=True)

    # Inicializar extensiones
    from app.extensions import login_manager, csrf
    login_manager.init_app(app)
    csrf.init_app(app)
    from app.security import init_security
    init_security(app)

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
