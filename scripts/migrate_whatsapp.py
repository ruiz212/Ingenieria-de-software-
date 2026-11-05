"""Explicit target required; loads .env when present for --connection-env."""
import argparse
import os
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import pyodbc
from app.qa_safety import require_qa_string


def migrate(conn):
    sql = (Path(__file__).resolve().parents[1] / 'database/06_whatsapp_bot.sql').read_text(encoding='utf-8')
    try:
        for batch in re.split(r'^\s*GO\s*$', sql, flags=re.MULTILINE | re.IGNORECASE):
            if batch.strip():
                conn.cursor().execute(batch)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--allow-production', action='store_true')
    args = parser.parse_args()
    target = os.environ.get(args.connection_env, '')
    if not args.allow_production:
        require_qa_string(target)
    if not target:
        parser.error('La variable de conexión está vacía.')
    conn = pyodbc.connect(target)
    try:
        migrate(conn)
    finally:
        conn.close()
