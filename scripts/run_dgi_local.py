"""Inicia el sistema existente exclusivamente con una base QA explícita.

python scripts/run_dgi_local.py --connection-env TEST_DB_CONNECTION_STRING
No cambia .env, no aplica migraciones y no omite el inicio de sesión.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyodbc
from app import create_app
from config import Config
from scripts.demo_dgi import require_qa, create_demo_user


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--port', default=5065, type=int)
    parser.add_argument('--crear-usuario-demo', action='store_true', help='Crear cuenta QA independiente y mostrar acceso aleatorio')
    args = parser.parse_args()
    connection_string = os.environ[args.connection_env]
    connection = pyodbc.connect(connection_string)
    try:
        require_qa(connection)
        if not connection.cursor().execute("SELECT OBJECT_ID('DGI_Revisiones','U')").fetchone()[0]:
            raise ValueError('Ejecute primero scripts/migrate_dgi.py en esta base QA.')
        if args.crear_usuario_demo:
            credentials = create_demo_user(connection)
            connection.commit()
            print('Acceso SOLO a esta base QA:', credentials['usuario'], credentials['clave'], flush=True)
    finally:
        connection.close()
    class LocalConfig(Config):
        SQL_SERVER_CONNECTION_STRING = connection_string
        SESSION_COOKIE_SECURE = False
    app = create_app(LocalConfig)
    app.run(host='127.0.0.1', port=args.port, debug=False)
