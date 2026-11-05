"""Real templates/scripts, synthetic QR/quotes; no SQL, WhatsApp or external writes."""
import os
from pathlib import Path
import sys
from threading import Thread
from types import SimpleNamespace

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flask import Flask, render_template
from flask_login import LoginManager
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from app.models import User
from app.admin import admin_bp
from app.utils.qr import generar_qr_base64

app = Flask(__name__, template_folder=str(ROOT/'templates'), static_folder=str(ROOT/'static'))
app.secret_key = 'synthetic-browser-only'
login = LoginManager(app)
admin = User(9, 'synthetic', 'Administración de prueba', 1, 'Admin', totp_enabled=True)
login.request_loader(lambda req: admin)
app.register_blueprint(admin_bp)
app.jinja_env.globals.update(csrf_token=lambda: 'synthetic', css_url=lambda name: '/static/css/dist/'+name+'.css')
app.add_url_rule('/home', endpoint='hub.main_hub', view_func=lambda: '')
state = {'Activo': False, 'Estado': 'Esperando QR', 'ConnectionRevision': 3, 'ready': True,
         'needs_auth': True, 'Vinculado': False, 'QR': None}


@app.get('/')
def panel():
    return render_template('admin/whatsapp.html', installed=True, sid=1, state=state,
        sessions=[{'ID': 1, 'Telefono': '+50588888888', 'Modo': 'HUMANO', 'Avisos': False, 'Revision': 1}],
        messages=[{'Tipo': 'Cliente', 'Estado': 'Procesado', 'Creado': '04/11/2026',
                   'Texto': 'Quisiera cotizar un pastel para 20 personas con esta referencia.'}])


@app.get('/pos')
def pos():
    return render_template('pos.html', productos=[], ingredientes=[], categorias=[], configuracion={},
                           user=admin, turno_activo=SimpleNamespace(ID=1), mes_actual=11)


def quote(qid, channel='WhatsApp'):
    return dict(id=qid, cliente='<img src=x onerror=alert(1)>', telefono='+50588888888',
                fecha_entrega='2026-12-01', precio_cotizado=None, estado='Pendiente',
                especificaciones='Pastel para 20 personas', ruta_imagen='', canal=channel)


server = make_server('127.0.0.1', 0, app, threaded=True)
Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(reduced_motion='reduce')
        # All data is local and synthetic. Prevent any POST from reaching an app route.
        context.route('**/*', lambda route: route.abort() if route.request.method not in ('GET', 'HEAD') or
                      not route.request.url.startswith(f'http://127.0.0.1:{server.server_port}') else route.continue_())
        context.route('**/auth/ping', lambda route: route.fulfill(json={'ok': True}))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        current = state.copy()
        page.route('**/admin/whatsapp/estado', lambda route: route.fulfill(json=current))
        for width in (390, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_load_state('networkidle')
            expect(page.locator('#wa-link-password')).to_be_visible()
            assert page.locator('#wa-link-otp').get_attribute('required') is not None
            assert page.locator('#wa-qr').is_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
            page.screenshot(path=str(ROOT/f'scratch/whatsapp-linking-{width}.png'), full_page=True)
        page.locator('#wa-link-password').fill('unsent synthetic value')
        current.update(needs_auth=False, QR=generar_qr_base64('synthetic-not-a-whatsapp-login'))
        expect(page.locator('#wa-qr')).to_be_visible(timeout=6000)
        assert page.locator('#wa-link-password').input_value() == 'unsent synthetic value'
        current.update(QR=None, Vinculado=True, Estado='Conectado', CuentaTelefono='+50588888888')
        expect(page.locator('#wa-qr')).to_be_hidden(timeout=6000)
        expect(page.locator('#wa-account')).to_have_text('+50588888888')
        page.locator('#wa-unlink-details summary').click()
        assert page.locator('#wa-unlink-confirm').get_attribute('pattern') == 'DESVINCULAR'
        current['ConnectionRevision'] = 4
        expect(page.locator('#wa-link-details button')).to_be_disabled(timeout=6000)
        print('Panel: mobile/desktop, private QR refresh, drafts and stale-account protection passed')

        # Existing POS template and script: new requests must arrive without stealing focus.
        quotes = [quote(1, 'Web')]
        page.route('**/api/**', lambda route: route.fulfill(json=quotes if '/cotizaciones/pendientes' in route.request.url else {'tipo_cambio': 36.6}))
        page.goto(f'http://127.0.0.1:{server.server_port}/pos?solicitudes=1')
        page.wait_for_load_state('networkidle')
        expect(page.locator('#pedidos-clientes-modal')).to_be_visible()
        expect(page.locator('#precio-cotizacion-1')).to_be_visible()
        page.locator('#precio-cotizacion-1').fill('450')
        quotes.append(quote(2))
        expect(page.locator('#precio-cotizacion-2')).to_be_visible(timeout=15000)
        assert page.locator('#precio-cotizacion-1').input_value() == '450'
        assert page.evaluate('document.activeElement.id') == 'precio-cotizacion-1'
        assert page.locator('#cotizaciones-pendientes-list img').count() == 0, 'Customer text rendered as HTML'
        expect(page.locator('#cotizaciones-pendientes-list')).to_contain_text('WhatsApp')
        assert not errors, errors
        print('POS: incoming WhatsApp quote visible, editable price/focus preserved, HTML escaped')
        browser.close()
finally:
    server.shutdown()
