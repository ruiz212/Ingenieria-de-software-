# app/kiosco/__init__.py
# Blueprint independiente para el Kiosco de Marcaje de Asistencia.
# Este módulo es público (sin login) ya que se usa en un dispositivo
# dedicado en la entrada del local.

from flask import Blueprint

kiosco_bp = Blueprint('kiosco', __name__, url_prefix='/kiosco')

from app.kiosco import routes  # noqa: E402, F401
