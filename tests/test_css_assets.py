"""The stylesheet build must never silently drop a page's styles."""
import json
import re
from pathlib import Path

import pytest
from flask import Flask

from scripts.build_css import build_css


def sources(tmp_path):
    root = tmp_path / 'static' / 'css'
    (root / 'base').mkdir(parents=True)
    (root / 'base' / 'tokens.css').write_text(':root { --color: brown; }', encoding='utf-8')
    (root / 'page.css').write_text('.page { color: var(--color); }', encoding='utf-8')
    (root / 'sources.json').write_text(json.dumps({'app':['base/tokens.css','page.css']}), encoding='utf-8')
    return root


def test_build_is_deterministic_and_versions_content(tmp_path):
    root = sources(tmp_path)
    first = build_css(root)
    output = (root / first['app']['file']).read_bytes()
    assert output.index(b'--color: brown') < output.index(b'.page')
    assert build_css(root) == first
    assert (root / first['app']['file']).read_bytes() == output
    (root / 'page.css').write_text('.page { color: green; }', encoding='utf-8')
    assert build_css(root)['app']['version'] != first['app']['version']


def test_missing_source_does_not_change_existing_outputs(tmp_path):
    root = sources(tmp_path)
    build_css(root)
    previous = {p:p.read_bytes() for p in (root / 'dist').rglob('*') if p.is_file()}
    (root / 'page.css').unlink()
    with pytest.raises(FileNotFoundError):
        build_css(root)
    assert all(p.read_bytes() == content for p,content in previous.items())


def test_build_rejects_paths_outside_css_directory(tmp_path):
    root = sources(tmp_path)
    (root / 'sources.json').write_text(json.dumps({'app':['../escape.css']}), encoding='utf-8')
    with pytest.raises(ValueError):
        build_css(root)


def test_check_detects_outdated_output_without_rewriting_it(tmp_path):
    root = sources(tmp_path)
    assets = build_css(root)
    output = root / assets['app']['file']
    output.write_text('outdated', encoding='utf-8')
    with pytest.raises(ValueError, match='desactualizado'):
        build_css(root, check=True)
    assert output.read_text(encoding='utf-8') == 'outdated'


def test_jinja_resolves_built_asset_and_reloads_manifest(tmp_path):
    from app.assets import init_assets
    root = sources(tmp_path)
    assets = build_css(root)
    app = Flask(__name__, static_folder=str(root.parent))
    init_assets(app)
    with app.test_request_context():
        url = app.jinja_env.globals['css_url']('app')
        assert url.endswith(f"/css/dist/app.css?v={assets['app']['version']}")
        (root / 'page.css').write_text('.page { color: blue; }', encoding='utf-8')
        updated = build_css(root)
        assert app.jinja_env.globals['css_url']('app').endswith(updated['app']['version'])
        with pytest.raises(KeyError):
            app.jinja_env.globals['css_url']('missing')


def test_templates_reference_built_packages_and_keep_presentation_external():
    """Catch broken package links and accidental reintroduction of embedded CSS."""
    root = Path(__file__).resolve().parents[1]
    css = root / 'static' / 'css'
    packages = json.loads((css / 'sources.json').read_text(encoding='utf-8'))
    for template in (root / 'templates').rglob('*.html'):
        text = template.read_text(encoding='utf-8')
        assert not re.search(r'<style\b|\sstyle=', text), str(template)
        for package in re.findall(r"css_url\('([^']+)'\)", text):
            assert package in packages, (str(template), package)
