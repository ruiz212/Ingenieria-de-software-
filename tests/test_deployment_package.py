import importlib.util
from pathlib import Path
from zipfile import ZipFile


def test_deployment_contains_runtime_and_excludes_credentials_and_user_files(tmp_path):
    spec = importlib.util.spec_from_file_location('build_deployment', Path(__file__).parents[1]/'scripts/build_deployment.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ['app/__init__.py', 'templates/admin/whatsapp.html', 'static/css/app.css',
                 'requirements.txt', 'requirements-whatsapp.txt', 'run.py', 'config.py',
                 'scripts/run_whatsapp.py', 'app/.env', 'static/uploads/private.jpg',
                 'instance/whatsapp_session.sqlite3', '.env', 'scratch/private.txt']:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic', encoding='utf-8')
    target = tmp_path/'deployment.zip'
    module.package(tmp_path, target)
    with ZipFile(target) as archive:
        names = set(archive.namelist())
    assert {'run.py', 'app/__init__.py', 'scripts/run_whatsapp.py', 'requirements-whatsapp.txt'} <= names
    assert not any('private' in name or '.env' in name or 'instance/' in name for name in names)
