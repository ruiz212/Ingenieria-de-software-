"""Startup must not pay for biometric inference before it is requested."""
import os
import subprocess
import sys
from types import SimpleNamespace


def test_biometric_proxy_delegates_to_shared_service(monkeypatch):
    from app.kiosco.routes import face_service
    calls = []
    service = SimpleNamespace(reconocer_rostro=lambda image: calls.append(image) or {'status': 'unknown'})
    monkeypatch.setitem(sys.modules, 'app.services.face_service', SimpleNamespace(face_service=service))
    assert face_service.reconocer_rostro('frame-1') == {'status': 'unknown'}
    assert face_service.reconocer_rostro('frame-2') == {'status': 'unknown'}
    assert calls == ['frame-1', 'frame-2']


def test_public_pages_do_not_load_biometric_models():
    result = subprocess.run(
        [sys.executable, '-c', """
import sys
from app import create_app
app = create_app()
app.config.update(TESTING=True)
with app.test_client() as client:
    assert client.get('/login').status_code == 200
    assert client.get('/kiosco/').status_code == 200
assert 'app.services.face_service' not in sys.modules
assert 'cv2' not in sys.modules
"""],
        env={**os.environ, 'PYTHON_DOTENV_DISABLED': '1', 'WHATSAPP_ENABLED': '0'},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
