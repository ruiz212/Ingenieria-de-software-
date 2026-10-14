"""Controles comunes a todos los módulos, incluidos los formularios AJAX."""
from flask import request, jsonify, current_app
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import BadRequest


def init_security(app):
    @app.errorhandler(BadRequest)
    def bad_request(error):
        if request.is_json or '/api/' in request.path:
            return jsonify(error='Solicitud inválida. Revise los datos enviados.'),400
        return 'Solicitud inválida.',400

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

    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if current_user.is_authenticated and not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
