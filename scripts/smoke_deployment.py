"""Import and exercise the actual ZIP outside the checkout; run Gunicorn on Linux."""
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_deployment import validate_archive


def smoke(archive):
    validate_archive(archive)
    env = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1', 'DB_CONNECTION_STRING': '',
           'TEST_DB_CONNECTION_STRING': '', 'WHATSAPP_ENABLED': '0', 'FLASK_DEBUG': '0',
           'PYTHONPATH': '', 'GUNICORN_CMD_ARGS': ''}
    with TemporaryDirectory(prefix='bakery-runtime-') as directory:
        with ZipFile(archive) as package:
            package.extractall(directory)
        subprocess.run([sys.executable, '-c', '''
import sys
from run import app
app.config.update(TESTING=True)
with app.test_client() as client:
    for path in ('/login', '/kiosco/'):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
assert 'cv2' not in sys.modules
assert 'app.services.face_service' not in sys.modules
'''], cwd=directory, env=env, check=True, timeout=60)
        if os.name == 'nt':
            print('Archive import and public pages verified; Gunicorn requires Linux CI.')
            return
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        with (Path(directory) / 'gunicorn-smoke.log').open('w+', encoding='utf-8') as log:
            process = subprocess.Popen(
                [sys.executable, '-m', 'gunicorn', '--config', 'gunicorn.conf.py',
                 '--bind', f'127.0.0.1:{port}', 'run:app'],
                cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                while process.poll() is None and time.monotonic() < deadline:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/login', timeout=3) as response:
                            if response.status == 200:
                                print('Gunicorn served login from extracted deployment ZIP.')
                                return
                    except (URLError, TimeoutError):
                        pass
                    time.sleep(0.25)
                log.seek(0)
                raise RuntimeError('Gunicorn smoke test failed:\n' + log.read())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == '__main__':
    smoke(sys.argv[1])
