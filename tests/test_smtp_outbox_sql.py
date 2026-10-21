"""Real SQL claims use only owned synthetic IDs; never drain the shared queue."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from app.services import smtp_alerts as alerts


@pytest.fixture
def sql_outbox():
    connection_string = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not connection_string:
        pytest.skip('Requires explicit guarded TEST_DB_CONNECTION_STRING for QA')
    cfg = dict(connection_string=connection_string, testing=True, rate_limit_seconds=300)
    conn = alerts._open_standalone_sql_connection(cfg)
    ids = []
    marker = 'QA_SMTP_' + uuid.uuid4().hex

    def create():
        payload = dict(origen='PYTHON_DB', procedimiento=marker, mensaje_error=marker,
                       username='QA SMTP recovery', parametros_json={'case': marker})
        error_id = alerts.record_error_in_db(payload, cfg, connection=conn)
        assert error_id is not None
        ids.append(error_id)
        assert alerts._enqueue_error(error_id, cfg, connection=conn)
        conn.commit()
        return error_id

    try:
        yield cfg, conn, create, ids
    finally:
        conn.rollback()
        # Synthetic forensic rows are retained. Exclude our queue rows from any
        # later real consumer without pretending a simulated email was delivered.
        for error_id in ids:
            conn.cursor().execute("UPDATE seguridad.AlertasSMTPOutbox SET Estado='Suppressed', ClaimToken=NULL, LeaseHasta=NULL WHERE ErrorID=?", error_id)
            conn.cursor().execute('UPDATE d SET ClaimToken=NULL, LeaseHasta=NULL FROM seguridad.AlertasSMTPDedup d JOIN seguridad.AlertasSMTPOutbox o ON o.DedupKey=d.DedupKey WHERE o.ErrorID=?', error_id)
        conn.commit()
        conn.close()


def test_sql_crossprocess_claim_crash_recovery_retry_and_suppression(sql_outbox, tmp_path):
    cfg, conn, create, _ = sql_outbox
    error_id = create()
    child = tmp_path / 'claim.py'
    child.write_text('''import json, os, sys
from app.services.smtp_alerts import _claim_alert
cfg=dict(connection_string=os.environ['TEST_DB_CONNECTION_STRING'], testing=True, rate_limit_seconds=300)
claim=_claim_alert(cfg, int(sys.argv[1]), seed_batch=0)
print(json.dumps(str(claim['ClaimToken']) if claim else None))
''', encoding='utf-8')
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=root, PYTHON_DOTENV_DISABLED='1')
    workers = [subprocess.Popen([sys.executable, str(child), str(error_id)], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    tokens = []
    for worker in workers:
        stdout, stderr = worker.communicate(timeout=30)
        assert worker.returncode == 0, stderr
        tokens.append(json.loads(stdout))
    assert sum(token is not None for token in tokens) == 1
    old_token = next(token for token in tokens if token)
    # Both processes have exited; their committed lease must survive the restart.
    assert alerts._claim_alert(cfg, error_id, seed_batch=0) is None
    # Simulate elapsed time on our own reservation, without sleeping five minutes.
    conn.cursor().execute('UPDATE seguridad.AlertasSMTPOutbox SET LeaseHasta=DATEADD(SECOND,-1,SYSUTCDATETIME()) WHERE ErrorID=?', error_id)
    conn.cursor().execute('UPDATE d SET LeaseHasta=DATEADD(SECOND,-1,SYSUTCDATETIME()) FROM seguridad.AlertasSMTPDedup d JOIN seguridad.AlertasSMTPOutbox o ON o.DedupKey=d.DedupKey WHERE o.ErrorID=?', error_id)
    conn.commit()
    recovered = alerts._claim_alert(cfg, error_id, seed_batch=0)
    assert recovered is not None
    assert str(recovered['ClaimToken']) != old_token
    assert alerts._complete_alert({'ID': error_id, 'ClaimToken': old_token}, cfg, True) is False
    assert alerts._complete_alert(recovered, cfg, False) is True
    row = conn.cursor().execute('SELECT Estado, Intentos, ClaimToken, DisponibleDesde FROM seguridad.AlertasSMTPOutbox WHERE ErrorID=?', error_id).fetchone()
    assert (row.Estado, row.Intentos, row.ClaimToken) == ('Pending', 2, None)
    conn.commit()
    assert alerts._claim_alert(cfg, error_id, seed_batch=0) is None  # retry is delayed
    # A different instance of the same error is immediately eligible after failure.
    second_id = create()
    second = alerts._claim_alert(cfg, second_id, seed_batch=0)
    assert second is not None
    assert alerts._complete_alert(second, cfg, True) is True
    notified = conn.cursor().execute('SELECT NotificadoSMTP FROM seguridad.BitacoraErrores WHERE ID=?', second_id).fetchone()
    assert notified[0] == 1
    conn.commit()
    third_id = create()
    assert alerts._claim_alert(cfg, third_id, seed_batch=0) is None
    suppressed = conn.cursor().execute('SELECT Estado FROM seguridad.AlertasSMTPOutbox WHERE ErrorID=?', third_id).fetchone()
    assert suppressed[0] == 'Suppressed'
    original = conn.cursor().execute('SELECT MensajeError, Username, NotificadoSMTP FROM seguridad.BitacoraErrores WHERE ID=?', error_id).fetchone()
    assert original.MensajeError.startswith('QA_SMTP_')
    assert original.Username == 'QA SMTP recovery'
    assert original.NotificadoSMTP == 0
    conn.commit()
