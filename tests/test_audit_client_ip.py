"""IP audit records use verified peer/proxy identity rather than arbitrary XFF."""
import pytest
from flask import jsonify, request

from app import create_app, db
from app.services import smtp_alerts


def make_app(trusted=(), hops=1):
    class Config:
        TESTING = True
        SECRET_KEY = 'synthetic-only'
        SMTP_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''
        TRUSTED_PROXY_CIDRS = trusted
        PROXY_X_FOR_HOPS = hops
    app = create_app(Config)

    @app.get('/_audit_ip')
    def audit_ip():
        return jsonify(peer=request.remote_addr, sql=db._effective_client_ip(), smtp=smtp_alerts._extract_request_context()['ip'])

    return app


@pytest.mark.parametrize('peer', ['192.0.2.10', '2001:db8::10'])
def test_forged_forwarded_for_cannot_replace_untrusted_peer(peer):
    response = make_app().test_client().get('/_audit_ip', headers={'X-Forwarded-For':'198.51.100.99'}, environ_base={'REMOTE_ADDR':peer})
    assert response.json == {'peer':peer, 'sql':peer, 'smtp':peer}


def test_only_configured_proxy_can_select_client_from_right_side():
    client = make_app(('203.0.113.0/24',)).test_client()
    response = client.get('/_audit_ip', headers={'X-Forwarded-For':'198.51.100.99, 192.0.2.20'}, environ_base={'REMOTE_ADDR':'203.0.113.7'})
    assert response.json == {'peer':'192.0.2.20', 'sql':'192.0.2.20', 'smtp':'192.0.2.20'}


def test_configuring_proxy_does_not_trust_other_peers():
    response = make_app(('203.0.113.0/24',)).test_client().get('/_audit_ip', headers={'X-Forwarded-For':'198.51.100.99'}, environ_base={'REMOTE_ADDR':'192.0.2.10'})
    assert response.json['sql'] == response.json['smtp'] == '192.0.2.10'


def test_invalid_forwarded_ip_is_not_recorded_as_an_audit_address():
    response = make_app(('203.0.113.0/24',)).test_client().get('/_audit_ip', headers={'X-Forwarded-For':'forged-not-an-ip'}, environ_base={'REMOTE_ADDR':'203.0.113.7'})
    assert response.json['sql'] == response.json['smtp'] == ''
