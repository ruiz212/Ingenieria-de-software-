"""Resolve versioned stylesheet URLs from the generated manifest."""
import json
from pathlib import Path

from flask import url_for


def init_assets(app):
    manifest_path = Path(app.static_folder) / 'css' / 'dist' / 'manifest.json'
    cached_stamp = None
    cached_assets = {}

    def css_url(name):
        nonlocal cached_stamp, cached_assets
        stat = manifest_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != cached_stamp:
            cached_assets = json.loads(manifest_path.read_text(encoding='utf-8'))
            cached_stamp = stamp
        asset = cached_assets[name]
        return url_for('static', filename=f"css/{asset['file']}", v=asset['version'])

    app.jinja_env.globals['css_url'] = css_url
