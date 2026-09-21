# app/pos/__init__.py

from flask import Blueprint

pos_bp = Blueprint('pos', __name__)

from app.pos import routes  # noqa: E402, F401
