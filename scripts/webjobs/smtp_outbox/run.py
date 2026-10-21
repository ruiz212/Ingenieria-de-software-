"""Continuous WebJob launcher. Package this file and settings.job as a ZIP.

The deployed app/runtime paths are explicit because App Service build/extraction
paths vary. The job never assumes the Kudu interpreter has app dependencies.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    required = ('SMTP_APP_ROOT', 'SMTP_WORKER_PYTHON', 'SMTP_WORKER_EXPECTED_DB')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print('WebJob requires: ' + ', '.join(missing), file=sys.stderr)
        return 2
    root = Path(os.environ['SMTP_APP_ROOT'])
    script = root / 'scripts' / 'process_pending_alerts.py'
    if not script.is_file():
        print('SMTP_APP_ROOT does not contain scripts/process_pending_alerts.py', file=sys.stderr)
        return 2
    os.chdir(root)
    python = os.environ['SMTP_WORKER_PYTHON']
    command = [python, str(script), '--loop', '--expected-db',
               os.environ['SMTP_WORKER_EXPECTED_DB'], '--batch', '20', '--interval', '15']
    if os.name == 'nt':
        # Windows execv does not preserve redirected pipes like POSIX exec.
        return subprocess.call(command)
    # Replace the Linux WebJob process so SIGTERM reaches the consumer directly.
    os.execv(python, command)


if __name__ == '__main__':
    raise SystemExit(main())
