# app/hub/__init__.py

from flask import Blueprint

hub_bp = Blueprint('hub', __name__)

from app.hub import routes  # noqa: E402, F401
