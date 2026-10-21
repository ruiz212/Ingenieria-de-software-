"""Render today's POS template without opening SQL or SMTP connections."""
import os
from pathlib import Path
import smtplib
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding='utf-8')

import pyodbc


def forbidden_network(*args, **kwargs):
    raise AssertionError('SQL and SMTP are forbidden in browser fixture rendering')


pyodbc.connect = forbidden_network
smtplib.SMTP = forbidden_network
smtplib.SMTP_SSL = forbidden_network

from app import create_app
from app.models import User
from flask import render_template


class Config:
    TESTING = True
    SECRET_KEY = 'isolated-browser-render'
    WTF_CSRF_ENABLED = False


app = create_app(Config)
with app.test_request_context('/pos'):
    print(render_template('pos.html', productos=[], ingredientes=[], categorias=[],
                          configuracion={}, user=User(90001, 'synthetic', 'Synthetic', 1, 'Estandar'),
                          turno_activo=type('Shift', (), {'ID': 1})(), mes_actual=10))
