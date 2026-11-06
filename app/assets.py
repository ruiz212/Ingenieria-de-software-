"""Resolve versioned stylesheet URLs from the generated manifest."""
import json
from pathlib import Path

from flask import url_for


def init_assets(app):
    manifest_path = Path(app.static_folder) / 'css' / 'dist' / 'manifest.json'
    cached_stamp = None
    cached_assets = {}
    reload_manifest = app.config.get('TEMPLATES_AUTO_RELOAD') is not False

    def css_url(name):
        nonlocal cached_stamp, cached_assets
        # Production assets change at deployment, together with the workers.
        # Avoid a filesystem round trip for each stylesheet in each template.
        stamp = None
        if reload_manifest:
            stat = manifest_path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        if not cached_assets or (reload_manifest and stamp != cached_stamp):
            cached_assets = json.loads(manifest_path.read_text(encoding='utf-8'))
            cached_stamp = stamp
        asset = cached_assets[name]
        return url_for('static', filename=f"css/{asset['file']}", v=asset['version'])

    app.jinja_env.globals['css_url'] = css_url
