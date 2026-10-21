"""Explicit, serial SMTP outbox consumer. Never reads .env or starts from Flask.

One bounded pass (default), or a supervised continuous process with --loop.
Connection/SMTP credentials come from environment; no CLI secret arguments.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Imports must never implicitly load an ordinary development database from .env.
os.environ['PYTHON_DOTENV_DISABLED'] = '1'

from app.services.smtp_alerts import (  # noqa: E402
    _open_standalone_sql_connection, get_smtp_config, retry_pending_alerts,
)
from scripts.migrate_esquemas_roles_sp import extract_expected_db_name  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', default='SMTP_WORKER_CONNECTION_STRING')
    parser.add_argument('--expected-db', required=True, help='Exact database name; checked before any delivery')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true', help='One bounded batch (default)')
    mode.add_argument('--loop', action='store_true', help='Continuous mode; requires an external process supervisor')
    parser.add_argument('--batch', type=int, default=20)
    parser.add_argument('--interval', type=int, default=15, help='Seconds between bounded passes in loop mode')
    parser.add_argument('--qa', action='store_true', help='Require a PanaderiaQA_ connection and actual database')
    args = parser.parse_args(argv)
    if not 1 <= args.batch <= 100 or not 1 <= args.interval <= 3600:
        parser.error('--batch must be 1..100 and --interval 1..3600')
    connection_string = os.environ.get(args.connection_env, '')
    if not connection_string:
        parser.error(f'{args.connection_env} must contain an explicit SQL connection string')
    try:
        if extract_expected_db_name(connection_string).lower() != args.expected_db.lower():
            parser.error('Connection database differs from --expected-db')
    except ValueError as exc:
        parser.error(str(exc))
    cfg = get_smtp_config({'SQL_SERVER_CONNECTION_STRING': connection_string, 'TESTING': args.qa})
    if os.environ.get('SMTP_ENABLED', '').lower() not in ('true', '1', 't', 'yes'):
        parser.error('Set SMTP_ENABLED=True explicitly to run the consumer')
    if not cfg.get('recipients') or not cfg.get('host'):
        parser.error('SMTP_HOST and SMTP_ALERT_RECIPIENTS are required')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        conn = _open_standalone_sql_connection(cfg)
        try:
            row = conn.cursor().execute('SELECT DB_NAME()').fetchone()
            if not row or str(row[0]).lower() != args.expected_db.lower():
                raise ValueError('Server returned a database different from --expected-db')
        finally:
            conn.close()
    except Exception:
        logging.error('SQL outbox startup check failed; no deliveries attempted')
        return 2
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    while not stopped.is_set():
        stats = retry_pending_alerts(args.batch, cfg)
        print(json.dumps(stats), flush=True)
        if not args.loop:
            return 1 if stats['errors'] or stats['failed'] else 0
        stopped.wait(args.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
