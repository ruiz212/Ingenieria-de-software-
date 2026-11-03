"""Migración integral de Esquemas (8), Roles de BD (6), Seguridad y Stored Procedures.

Uso:
  python scripts/migrate_esquemas_roles_sp.py --connection-env TEST_DB_CONNECTION_STRING
  python scripts/migrate_esquemas_roles_sp.py --connection-string "..."
"""
import argparse
import os
import re
from pathlib import Path
import pyodbc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SQL_FILES = (
    '01_esquemas_migracion.sql',
    '02_roles_y_seguridad_bd.sql',
    '03_stored_procedures.sql',
    '04_alertas_outbox.sql',
    '05_mercadotecnia.sql',
)


def split_sql_batches(sql_text: str):
    batches = re.split(r'^\s*GO\s*$', sql_text, flags=re.MULTILINE | re.IGNORECASE)
    return [b.strip() for b in batches if b and b.strip()]


def extract_expected_db_name(connection_string: str) -> str:
    values = re.findall(
        r'(?:^|;)\s*(?:DATABASE|INITIAL CATALOG)\s*=\s*(\{[^}]*\}|[^;]*)',
        str(connection_string),
        re.IGNORECASE,
    )
    if len(values) != 1 or not values[0].strip().strip('{}'):
        raise ValueError('La cadena de conexión debe especificar exactamente un nombre de base de datos (DATABASE / INITIAL CATALOG).')
    return values[0].strip().strip('{}')


def verify_target_database(connection, expected_db: str | None = None) -> str:
    row = connection.cursor().execute('SELECT DB_NAME()').fetchone()
    actual_db = str(row[0]).strip() if row and row[0] else ''
    if not actual_db:
        raise ValueError('No se pudo determinar el nombre de la base de datos conectada.')
    if expected_db and actual_db.lower() != expected_db.strip().lower():
        raise ValueError(
            f"Abortando migración: la base conectada [{actual_db}] no coincide con la esperada [{expected_db}]."
        )
    return actual_db


def migrate(connection, expected_db: str | None = None, sql_files: tuple | list | None = None):
    verify_target_database(connection, expected_db)
    db_dir = Path(__file__).resolve().parents[1] / 'database'
    cursor = connection.cursor()
    cursor.execute("EXEC sys.sp_set_session_context @key=N'allow_ddl_migration', @value=1;")
    files_to_run = sql_files if sql_files is not None else SQL_FILES
    try:
        for filename in files_to_run:
            sql_path = db_dir / filename
            sql_text = sql_path.read_text(encoding='utf-8')
            for batch in split_sql_batches(sql_text):
                cursor.execute(batch)
    finally:
        try:
            cursor.execute("EXEC sys.sp_set_session_context @key=N'allow_ddl_migration', @value=0;")
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--connection-env', help='Variable de entorno con la cadena de conexión ODBC')
    group.add_argument('--connection-string', help='Cadena de conexión ODBC explícita')
    parser.add_argument('--expected-db', help='Nombre exacto esperado de la base de datos antes de aplicar cambios')
    parser.add_argument('--file', help='Archivo SQL específico a ejecutar (opcional)')
    args = parser.parse_args()

    conn_str = os.environ.get(args.connection_env) if args.connection_env else args.connection_string
    if not conn_str:
        raise ValueError('La cadena de conexión indicada está vacía.')

    expected_db = args.expected_db or extract_expected_db_name(conn_str)
    conn = pyodbc.connect(conn_str)
    try:
        db_name = verify_target_database(conn, expected_db)
        target_files = (args.file,) if args.file else SQL_FILES
        migrate(conn, expected_db=db_name, sql_files=target_files)
        conn.commit()
        print(f'Migración de esquemas, roles y Stored Procedures completada en [{db_name}].')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
