"""Build an explicit runtime-only Azure ZIP; never copy the workspace wholesale."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT_FILES = {'run.py', 'config.py', 'requirements.txt', 'requirements.lock', 'requirements-whatsapp.txt'}
RUNTIME_DIRS = {'app', 'templates', 'static'}
SCRIPTS = {'scripts/run_whatsapp.py'}


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    candidates = [root/name for name in sorted(ROOT_FILES | SCRIPTS)]
    for directory in sorted(RUNTIME_DIRS):
        folder = root/directory
        if folder.is_dir():
            candidates.extend(folder.rglob('*'))
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidates):
            if not path.is_file() or path.is_symlink() or path == output:
                continue
            relative = path.relative_to(root)
            parts = relative.parts
            if any(part.startswith('.') or part in {'uploads', '__pycache__', 'node_modules'} for part in parts):
                continue
            if path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pyc', '.log', '.pem', '.key'}:
                continue
            name = relative.as_posix()
            if name in ROOT_FILES or name in SCRIPTS or parts[0] in RUNTIME_DIRS:
                archive.write(path, name)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parents[1], args.output))
