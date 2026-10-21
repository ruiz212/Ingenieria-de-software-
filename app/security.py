"""Controles comunes a todos los módulos, incluidos los formularios AJAX y alertas SMTP."""
from flask import g, request, jsonify, current_app
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import BadRequest, Forbidden, HTTPException


def notify_security_403(motivo: str | None = None, procedimiento: str = 'HTTP_403_FORBIDDEN') -> None:
    """Despacha alerta SMTP ante denegación de acceso HTTP 403 con deduplicación por petición."""
    if getattr(g, '_security_403_notified', False):
        return
    g._security_403_notified = True
    try:
        from app.services.smtp_alerts import notify_error
        msg = motivo or f"Intento de acceso no autorizado (HTTP 403) a {request.path}"
        notify_error(
            msg,
            origen='SEGURIDAD_AUTH',
            severidad='WARNING',
            numero_error=50403,
            procedimiento=procedimiento,
            esquema_origen='seguridad',
            ruta_http=request.path,
            persist_in_db=not current_app.testing,
        )
    except Exception:
        pass


def init_security(app):
    @app.errorhandler(BadRequest)
    def bad_request(error):
        if request.is_json or '/api/' in request.path:
            return jsonify(error='Solicitud inválida. Revise los datos enviados.'), 400
        return 'Solicitud inválida.', 400

    @app.before_request
    def validate_json_object():
        if request.is_json and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if not isinstance(request.get_json(silent=True), dict):
                raise BadRequest('La solicitud debe contener un objeto JSON válido.')

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.is_json or '/api/' in request.path:
            return jsonify(error='La sesión del formulario venció. Recargue la página e intente de nuevo.'), 400
        return 'La sesión del formulario venció. Recargue la página e intente de nuevo.', 400

    @app.errorhandler(ValueError)
    def validation_error(error):
        if request.is_json or '/api/' in request.path:
            return jsonify(error=str(error)), 400
        return 'Datos inválidos. Revise el formulario.', 400

    @app.errorhandler(Forbidden)
    def forbidden_error(error):
        notify_security_403(
            f"Intento de acceso no autorizado (HTTP 403) a {request.path}",
            procedimiento='HTTP_403_FORBIDDEN',
        )
        if request.is_json or '/api/' in request.path or request.accept_mimetypes.best == 'application/json':
            return jsonify(error='No tienes permisos para realizar esta acción.'), 403
        return 'Acceso denegado.', 403

    @app.errorhandler(Exception)
    def unhandled_exception_error(error):
        if isinstance(error, HTTPException):
            return error
        try:
            from app.services.smtp_alerts import notify_error
            notify_error(
                f"Error interno no controlado (HTTP 500) en {request.path}: {type(error).__name__}",
                origen='HTTP_500',
                severidad='CRITICAL',
                numero_error=50500,
                procedimiento='HTTP_500_UNHANDLED',
                esquema_origen='seguridad',
                detalle_tecnico=type(error).__name__,
                ruta_http=request.path,
                persist_in_db=not current_app.testing,
            )
        except Exception:
            pass
        if request.is_json or '/api/' in request.path or request.accept_mimetypes.best == 'application/json':
            return jsonify(error='Error interno del servidor al procesar la solicitud.'), 500
        return 'Error interno del servidor.', 500

    @app.after_request
    def secure_headers(response):
        if response.status_code == 403 and not getattr(g, '_security_403_notified', False):
            notify_security_403(
                f"Intento de acceso no autorizado (HTTP 403) a {request.path}",
                procedimiento='HTTP_403_RESPONSE',
            )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; connect-src 'self';",
        )
        response.headers.setdefault(
            'Strict-Transport-Security',
            'max-age=31536000; includeSubDomains',
        )
        if current_user.is_authenticated and not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
