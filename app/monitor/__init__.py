# app/monitor/__init__.py

from flask import Blueprint

monitor_bp = Blueprint('monitor', __name__)

from app.monitor import routes  # noqa: E402, F401
