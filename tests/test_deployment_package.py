import importlib.util
from pathlib import Path
from zipfile import ZipFile
import pytest


def test_deployment_contains_runtime_and_excludes_credentials_and_user_files(tmp_path):
    spec = importlib.util.spec_from_file_location('build_deployment', Path(__file__).parents[1]/'scripts/build_deployment.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ['app/__init__.py', 'templates/admin/whatsapp.html', 'static/css/app.css',
                 'requirements.txt', 'requirements.lock', 'requirements-whatsapp.txt',
                 '.deployment', 'gunicorn.conf.py', 'run.py', 'config.py',
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


@pytest.mark.parametrize('missing', ['run.py', 'app/__init__.py', 'gunicorn.conf.py', 'requirements.lock', '.deployment'])
def test_incomplete_source_is_rejected_before_writing_archive(tmp_path, missing):
    from scripts.build_deployment import package
    required = ['run.py', 'config.py', 'gunicorn.conf.py', 'requirements.txt',
                'requirements.lock', 'requirements-whatsapp.txt', '.deployment', 'app/__init__.py']
    for name in required:
        if name != missing:
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic', encoding='utf-8')
    output = tmp_path / 'deployment.zip'
    with pytest.raises(ValueError, match='Missing runtime files'):
        package(tmp_path, output)
    assert not output.exists()


def test_archive_contains_oryx_build_configuration(tmp_path):
    from scripts.build_deployment import package
    output = tmp_path / 'deployment.zip'
    package(Path(__file__).parents[1], output)
    with ZipFile(output) as archive:
        assert b'SCM_DO_BUILD_DURING_DEPLOYMENT = true' in archive.read('.deployment')
        assert archive.testzip() is None


def test_application_imports_and_serves_public_pages_from_extracted_archive(tmp_path):
    from scripts.build_deployment import package
    from scripts.smoke_deployment import smoke
    archive = package(Path(__file__).parents[1], tmp_path / 'deployment.zip')
    smoke(archive)
