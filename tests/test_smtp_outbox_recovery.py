"""Regressions for transport reservations; SMTP/SQL boundaries are isolated."""
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
import os
import subprocess
import sys
import json

from flask import Flask
import pytest

from app.services import smtp_alerts as alerts


@pytest.fixture
def cfg():
    alerts.reset_rate_limit_cache()
    return dict(enabled=True, recipients=['qa@example.test'], from_email='qa@example.test',
                rate_limit_seconds=300, connection_string='', testing=True)


def test_simultaneous_same_error_has_one_transport_attempt(monkeypatch, cfg):
    entered, release = threading.Event(), threading.Event()
    deliveries = []

    def send(*args):
        deliveries.append('sent')
        entered.set()
        if len(deliveries) == 1:
            assert release.wait(5)
        return True

    monkeypatch.setattr(alerts, 'send_smtp_message', send)
    payload = dict(mensaje_error='same failure', persist_in_db=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(alerts._dispatch_worker, dict(payload), cfg)
        assert entered.wait(5)
        second = pool.submit(alerts._dispatch_worker, dict(payload), cfg)
        try:
            result = second.result(timeout=2)
            assert result['rate_limited'] is True
        finally:
            release.set()
        assert first.result(timeout=5)['sent'] is True
    assert deliveries == ['sent']


def test_transport_failure_releases_reservation(monkeypatch, cfg):
    def failure(*args):
        raise OSError('simulated outage')

    monkeypatch.setattr(alerts, 'send_smtp_message', failure)
    payload = dict(mensaje_error='recoverable', persist_in_db=False)
    assert alerts._dispatch_worker(dict(payload), cfg)['sent'] is False
    monkeypatch.setattr(alerts, 'send_smtp_message', lambda *args: True)
    assert alerts._dispatch_worker(dict(payload), cfg)['sent'] is True


def test_async_persists_before_return_without_spawning_threads(monkeypatch):
    app = Flask(__name__)
    app.config.update(SMTP_ASYNC=True, SMTP_ENABLED=True, SMTP_ALERT_RECIPIENTS='qa@example.test')
    stored = []
    monkeypatch.setattr(alerts, 'record_error_in_db', lambda *args, **kwargs: 451)
    monkeypatch.setattr(alerts, '_enqueue_error', lambda error_id, *args, **kwargs: stored.append(error_id) or True,
                        raising=False)

    def unexpected_thread(*args, **kwargs):
        pytest.fail('notify_error must persist synchronously, not start one daemon per event')

    monkeypatch.setattr(alerts.threading, 'Thread', unexpected_thread)
    with app.app_context():
        result = alerts.notify_error('durable event')
    assert result['error_id'] == 451
    assert result['queued'] is True
    assert stored == [451]


def test_enqueue_failure_does_not_report_durable_queue_success(monkeypatch):
    app = Flask(__name__)
    app.config.update(SMTP_ASYNC=True, SMTP_ENABLED=True)
    monkeypatch.setattr(alerts, 'record_error_in_db', lambda *args, **kwargs: 452)
    monkeypatch.setattr(alerts, '_enqueue_error', lambda *args, **kwargs: False, raising=False)
    with app.app_context():
        result = alerts.notify_error('queue unavailable')
    assert result['error_id'] == 452
    assert result['queued'] is False
    assert result['sent'] is False


@pytest.mark.parametrize('persist_in_db', [True, False])
def test_async_without_durable_id_uses_bounded_transport_fallback(monkeypatch, persist_in_db):
    app = Flask(__name__)
    app.config.update(SMTP_ASYNC=True, SMTP_ENABLED=True, SMTP_ALERT_RECIPIENTS='qa@example.test')
    attempts = []

    def record(*args, **kwargs):
        attempts.append('record')
        return None

    monkeypatch.setattr(alerts, 'record_error_in_db', record)
    monkeypatch.setattr(alerts, 'send_smtp_message', lambda *args: True)
    with app.app_context():
        result = alerts.notify_error('DB unavailable ' + str(persist_in_db), persist_in_db=persist_in_db)
    assert result['sent'] is True
    assert result['queued'] is False
    assert attempts == (['record'] if persist_in_db else [])


def test_saturated_dispatch_preserves_persisted_error(monkeypatch, cfg):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(alerts, '_SEND_SLOTS', slots, raising=False)
    monkeypatch.setattr(alerts, '_enqueue_error', lambda *args, **kwargs: True, raising=False)
    monkeypatch.setattr(alerts, 'send_smtp_message', lambda *args: pytest.fail('no transport slot available'))
    result = alerts._dispatch_worker(dict(error_id=453, mensaje_error='saturated'), cfg)
    assert result['sent'] is False
    assert result['queued'] is True


@pytest.mark.parametrize('batch', [0, -1, 101, 100000])
def test_worker_rejects_unbounded_or_empty_batches(batch, cfg):
    with pytest.raises(ValueError):
        alerts.retry_pending_alerts(batch, cfg)


def test_consumer_cli_exposes_once_loop_and_requires_explicit_connection():
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'process_pending_alerts.py'
    help_result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0, help_result.stderr
    assert '--loop' in help_result.stdout
    env = dict(os.environ, SMTP_WORKER_CONNECTION_STRING='', PYTHON_DOTENV_DISABLED='1')
    result = subprocess.run([sys.executable, str(script), '--expected-db', 'PanaderiaQA_Prevalidacion_20261015'],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'SMTP_WORKER_CONNECTION_STRING' in result.stderr


def test_business_connection_enqueues_without_smtp_before_caller_commit(monkeypatch, cfg):
    monkeypatch.setattr(alerts, '_enqueue_error', lambda *args, **kwargs: True)
    monkeypatch.setattr(alerts, 'send_smtp_message', lambda *args: pytest.fail('uncommitted business transaction'))
    monkeypatch.setattr(alerts, '_claim_alert', lambda *args, **kwargs: pytest.fail('claiming within caller transaction'))
    result = alerts._dispatch_worker(dict(error_id=454, mensaje_error='transactional'), cfg, connection=object())
    assert result['queued'] is True
    assert result['sent'] is False


def test_consumer_rejects_caller_owned_transaction(cfg):
    with pytest.raises(ValueError, match='connection'):
        alerts.retry_pending_alerts(20, cfg, connection=object())


def test_email_recovery_masks_json_text_from_sql_only_error(cfg):
    message = alerts.build_alert_email(dict(mensaje_error='test', parametros_json='{"password":"SQLOnlySecret", "nested":{"token":"AnotherSecret"}}'),
                                       cfg['recipients'], cfg['from_email'])
    text = message.get_body(preferencelist=('plain',)).get_content()
    assert 'SQLOnlySecret' not in text
    assert 'AnotherSecret' not in text
    assert '***MASKED***' in text


def test_notify_masks_text_secrets_before_persistence(monkeypatch):
    app = Flask(__name__)
    app.config.update(SMTP_ASYNC=True, SMTP_ENABLED=True)
    persisted = []

    def record(payload, *args, **kwargs):
        persisted.append(dict(payload))
        return 456

    monkeypatch.setattr(alerts, 'record_error_in_db', record)
    monkeypatch.setattr(alerts, '_enqueue_error', lambda *args, **kwargs: True)
    with app.app_context():
        result = alerts.notify_error('Invoice failure password=PersistSecret remain-visible',
                                     detalle_tecnico='{"token":"PersistToken", "context":"keep-me"}')
    assert result['queued'] is True
    assert persisted[0]['mensaje_error'] == 'Invoice failure password=***MASKED*** remain-visible'
    assert json.loads(persisted[0]['detalle_tecnico']) == {'token': '***MASKED***', 'context': 'keep-me'}


def test_webjob_entrypoint_starts_explicit_worker_runtime(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'process_pending_alerts.py').write_text('import sys,json; print(json.dumps(sys.argv[1:]))', encoding='utf-8')
    runner = Path(__file__).resolve().parents[1] / 'scripts' / 'webjobs' / 'smtp_outbox' / 'run.py'
    env = dict(os.environ, SMTP_APP_ROOT=str(tmp_path), SMTP_WORKER_PYTHON=sys.executable,
               SMTP_WORKER_EXPECTED_DB='PanaderiaQA_Prevalidacion_20261015')
    result = subprocess.run([sys.executable, str(runner)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ['--loop', '--expected-db', 'PanaderiaQA_Prevalidacion_20261015',
                                       '--batch', '20', '--interval', '15']
