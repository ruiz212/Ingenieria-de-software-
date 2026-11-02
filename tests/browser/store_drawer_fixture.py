"""Keyboard check for the public bag with synthetic data and no SQL/API writes."""
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

from flask import Flask, render_template
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parents[2]
app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
app.secret_key = 'ui-fixture-only'
app.jinja_env.globals['css_url'] = lambda name: f'/static/css/dist/{name}.css'
app.jinja_env.globals['csrf_token'] = lambda: 'synthetic-token'
visitor = SimpleNamespace(is_authenticated=False, rol_nombre='Invitado', id=0,
                          nombre='Invitado', telefono='', fecha_nacimiento=None)


@app.get('/')
def store():
    return render_template('tienda.html', user=visitor, current_user=visitor,
                           productos=[], ingredientes=[], categorias=[], recomendaciones=[],
                           configuracion={}, mes_actual=11)


server = make_server('127.0.0.1', 0, app)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        page.route('**/*', lambda route: route.abort() if route.request.method not in ('GET', 'HEAD') else route.continue_())
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        trigger = page.locator('#btn-abrir-carrito-nav')
        trigger.click()
        assert page.locator('#cartDrawer').get_attribute('aria-modal') == 'true'
        assert page.evaluate("document.activeElement.id") == 'btn-cerrar-drawer-carrito'
        assert page.locator('main').evaluate('(node) => node.inert')
        page.screenshot(path=str(ROOT / 'scratch' / 'store-bag-390.png'), animations='disabled')
        page.keyboard.press('Shift+Tab')
        assert page.evaluate("document.activeElement.hasAttribute('data-browse-products')")
        page.keyboard.press('Escape')
        assert page.evaluate("document.activeElement.id") == 'btn-abrir-carrito-nav'
        assert not page.locator('main').evaluate('(node) => node.inert')
        trigger.click()
        page.locator('[data-browse-products]').click()
        assert page.evaluate("document.activeElement.id") == 'tienda-search-input'
        page.evaluate('window.abrirModalEncargo(true)')
        assert page.evaluate("document.activeElement.id") == 'modal-nombre-cliente'
        assert page.locator('main').evaluate('(node) => node.inert')
        page.locator('#encargo-modal button:visible').last.focus()
        page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement.closest('#encargo-modal') !== null")
        page.keyboard.press('Escape')
        assert not page.locator('#encargo-modal').is_visible()
        assert page.evaluate("document.activeElement.id") == 'btn-abrir-carrito-nav'
        assert not page.locator('main').evaluate('(node) => node.inert')
        page.evaluate("carrito.push({id: 1, nombre: 'Pan', precio: 10, cantidad: 1, categoria: 'Pan'}); document.getElementById('btn-realizar-pedido').disabled = false")
        trigger.click()
        page.locator('#btn-realizar-pedido').click()
        assert page.locator('#encargo-modal').is_visible()
        assert not page.locator('#cartDrawer').evaluate("node => node.classList.contains('open')")
        assert page.evaluate("document.activeElement.id") == 'modal-nombre-cliente'
        page.keyboard.press('Escape')
        for width in (320, 390, 768, 1024, 1366):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        browser.close()
    print('Store bag keyboard/focus fixture: passed; no page overflow at 320–1366 px')
finally:
    server.shutdown()
    thread.join(timeout=2)
