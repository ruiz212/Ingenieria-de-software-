"""ZipDeploy must wait for this deployment and never leak publish credentials."""
from pathlib import Path
from types import SimpleNamespace
import pytest

PROFILE = '''<publishData><publishProfile publishMethod="MSDeploy"
publishUrl="bakery.scm.azurewebsites.net:443" msdeploySite="bakery"
userName="synthetic-user" userPWD="synthetic-secret"
destinationAppUrl="https://bakery.azurewebsites.net" /></publishData>'''


def load_module():
    import importlib.util
    path = Path(__file__).parents[1] / 'scripts/deploy_azure.py'
    spec = importlib.util.spec_from_file_location('deploy_azure', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(status=200, data=None, headers=None, text=''):
    return SimpleNamespace(status_code=status, headers=headers or {}, text=text,
                           json=lambda: data)


class Session:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.auth = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.replies)


@pytest.fixture
def runtime_archive(tmp_path):
    from scripts.build_deployment import REQUIRED_FILES
    from zipfile import ZipFile
    path = tmp_path / 'deployment.zip'
    with ZipFile(path, 'w') as archive:
        for name in REQUIRED_FILES:
            archive.writestr(name, 'synthetic')
    return path


def test_profile_uses_scm_credentials_and_checks_target():
    module = load_module()
    endpoint, credentials, public_url = module.publish_target(PROFILE, 'bakery')
    assert endpoint == 'https://bakery.scm.azurewebsites.net'
    assert credentials == ('synthetic-user', 'synthetic-secret')
    assert public_url == 'https://bakery.azurewebsites.net'
    with pytest.raises(ValueError, match='target'):
        module.publish_target(PROFILE, 'another-app')


def test_failed_deployment_never_counts_as_success(monkeypatch):
    module = load_module()
    session = Session([response(data={'status': 3})])
    with pytest.raises(RuntimeError, match='failed'):
        module.wait_for_deployment(session, 'https://bakery.scm.azurewebsites.net/api/deployments/123', 60)


def test_waits_for_specific_deployment_until_success(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    session = Session([response(data={'status': 1}), response(data={'status': 4})])
    url = 'https://bakery.scm.azurewebsites.net/api/deployments/123'
    module.wait_for_deployment(session, url, 60)
    assert [call[1] for call in session.calls] == [url, url]


def test_zipdeploy_rejects_foreign_polling_url(runtime_archive, monkeypatch):
    module = load_module()
    session = Session([response(202, headers={'Location': 'https://example.org/steal'})])
    monkeypatch.setattr(module.requests, 'Session', lambda: session)
    with pytest.raises(ValueError, match='origin'):
        module.deploy(runtime_archive, PROFILE, 'bakery')
    assert len(session.calls) == 1
    assert '/api/zipdeploy?isAsync=true' in session.calls[0][1]
    assert session.calls[0][2]['allow_redirects'] is False


def test_missing_oryx_manifest_fails_release(runtime_archive, monkeypatch):
    module = load_module()
    session = Session([
        response(202, headers={'Location': '/api/deployments/123'}),
        response(data={'status': 4}),
        response(404),
    ])
    monkeypatch.setattr(module.requests, 'Session', lambda: session)
    with pytest.raises(RuntimeError, match='Oryx'):
        module.deploy(runtime_archive, PROFILE, 'bakery')


def test_login_probe_does_not_use_publish_credentials(monkeypatch):
    module = load_module()
    session = Session([response(200, text='<form><input name="csrf_token"></form>')])
    monkeypatch.setattr(module.requests, 'Session', lambda: session)
    module.wait_for_login('https://bakery.azurewebsites.net', 30)
    assert session.auth is None
    assert session.calls[0][1] == 'https://bakery.azurewebsites.net/login'


def test_http_error_does_not_echo_response_secrets():
    module = load_module()
    session = Session([response(401, text='synthetic-secret')])
    with pytest.raises(RuntimeError) as error:
        module.request(session, 'GET', 'https://bakery.scm.azurewebsites.net/api/deployments/123')
    assert '401' in str(error.value)
    assert 'synthetic-secret' not in str(error.value)


def test_release_requires_oryx_and_login_after_success(runtime_archive, monkeypatch):
    module = load_module()
    deployment_session = Session([
        response(202, headers={'Location': '/api/deployments/123'}),
        response(data={'status': 4}),
        response(text='virtualEnvName = "antenv"'),
    ])
    public_session = Session([response(text='<input name="csrf_token">')])
    sessions = iter([deployment_session, public_session])
    monkeypatch.setattr(module.requests, 'Session', lambda: next(sessions))
    module.deploy(runtime_archive, PROFILE, 'bakery')
    assert deployment_session.auth == ('synthetic-user', 'synthetic-secret')
    assert public_session.auth is None
    assert deployment_session.calls[-1][1].endswith('/api/vfs/site/wwwroot/oryx-manifest.toml')


@pytest.mark.parametrize('probe', ['wait_for_deployment', 'wait_for_login'])
def test_pending_deployment_or_unready_login_times_out(probe, monkeypatch):
    module = load_module()
    ticks = iter([0, 0, 61])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    session = Session([response(data={'status': 1}, text='default Azure page')])
    monkeypatch.setattr(module.requests, 'Session', lambda: session)
    with pytest.raises(RuntimeError, match='Timed out|not ready'):
        if probe == 'wait_for_deployment':
            module.wait_for_deployment(session, 'https://bakery.scm.azurewebsites.net/api/deployments/123', 60)
        else:
            module.wait_for_login('https://bakery.azurewebsites.net', 60)
