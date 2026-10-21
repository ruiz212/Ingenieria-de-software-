"""An explicit administrator transport probe must bypass ordinary event dedup."""
from app import create_app
from app.models import User
from app.services import smtp_alerts


def test_manual_probe_requests_a_fresh_transport_attempt(monkeypatch):
    class Config:
        TESTING = True
        SECRET_KEY = 'synthetic-only'
        WTF_CSRF_ENABLED = False
        SMTP_ENABLED = False
    app = create_app(Config)
    monkeypatch.setattr(app.login_manager, '_user_callback', lambda _: User(90001, 'synthetic', 'Synthetic Only', 1, 'SuperAdmin'))
    monkeypatch.setattr('app.auth.routes.totp_is_required', lambda: False)

    def saturated_dedup_window(*args, **kwargs):
        # External SMTP and SQL are replaced; an ordinary duplicate is already
        # suppressed, while an explicit forced probe can attempt transport.
        return {'error_id':90001, 'sent':bool(kwargs.get('force_send')), 'rate_limited':not bool(kwargs.get('force_send'))}

    monkeypatch.setattr(smtp_alerts, 'notify_error', saturated_dedup_window)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'emp_90001'
        session['_fresh'] = True
    response = client.post('/admin/api/seguridad/smtp-test', json={})
    assert response.status_code == 200
    assert response.json['smtp_enviado'] is True
    assert response.json['rate_limited'] is False
