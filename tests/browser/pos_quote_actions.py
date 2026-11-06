"""Real POS scripts with synthetic HTTP; never contacts SQL or WhatsApp."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HTML = subprocess.check_output([sys.executable, str(ROOT / 'tests/browser/render_web_reference_fixture.py')],
                               cwd=ROOT, text=True, encoding='utf-8')
QUOTE = dict(id=101, cliente='Cliente sintético', telefono='88887777',
             fecha_entrega='2026-12-01', fecha_solicitud='2026-11-06 10:00',
             especificaciones='Pastel de prueba', ruta_imagen=None, estado='Cotizada',
             canal='WhatsApp', precio_cotizado=450)


def fixture(browser, width=1440):
    context = browser.new_context(viewport={'width': width, 'height': 1000}, reduced_motion='reduce')
    page = context.new_page()
    state = {'quotes': [copy.deepcopy(QUOTE)], 'price_error': None, 'posts': []}
    def route(request):
        r = request.request
        path = urlsplit(r.url).path
        if path == '/pos':
            return request.fulfill(content_type='text/html', body=HTML)
        if path.startswith('/static/'):
            target = (ROOT / path.lstrip('/')).resolve()
            if target.is_relative_to(ROOT / 'static') and target.is_file():
                return request.fulfill(path=str(target))
            return request.fulfill(status=404)
        if path == '/api/cotizaciones/pendientes':
            return request.fulfill(json=state['quotes'])
        if path.startswith('/api/cotizaciones/101/'):
            state['posts'].append(r)
            if not r.headers.get('x-csrftoken'):
                return request.fulfill(status=400, json={'error': 'Falta CSRF'})
            if 'application/json' in r.headers.get('content-type', ''):
                try:
                    payload = r.post_data_json
                except Exception:
                    payload = None
                if not isinstance(payload, dict):
                    return request.fulfill(status=400, json={'error': 'Solicitud inválida. Revise los datos enviados.'})
            if path.endswith('/cotizar') and state['price_error']:
                return request.fulfill(status=409, json={'error': state['price_error']})
            return request.fulfill(json={'mensaje': 'Operación guardada'})
        if path.startswith('/api/') or path.startswith('/admin/api/'):
            return request.fulfill(json={'tipo_cambio': 36.6})
        return request.abort()
    page.route('**/*', route)
    page.goto('https://pos.audit/pos', wait_until='networkidle')
    page.locator('#btn-ver-pedidos-clientes').click()
    page.locator('[data-quote-id="101"]').wait_for()
    return context, page, state


def refresh(page):
    with page.expect_response('**/api/cotizaciones/pendientes'):
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(150)


def run():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        def case(name, check, width=1440):
            context, page, state = fixture(browser, width)
            try:
                check(page, state)
                print('PASS', name)
            except Exception as error:
                errors.append((name, str(error)))
                print('FAIL', name, str(error)[:350])
            finally:
                context.close()
        def update(page, state):
            page.locator('#precio-cotizacion-101').fill('680')
            page.get_by_role('button', name='Actualizar Precio', exact=True).click()
            page.locator('[data-action="confirm"]').click()
            page.get_by_text('Precio asignado correctamente', exact=True).wait_for(timeout=3000)
            assert state['posts'][-1].post_data_json == {'precio': 680}
        def rejected(page, state):
            page.get_by_role('button', name='Rechazar', exact=True).click()
            page.locator('[data-action="confirm"]').click()
            page.get_by_text('Solicitud rechazada', exact=True).wait_for(timeout=3000)
        def invalid_price(page, state):
            state['price_error'] = 'La solicitud fue aceptada. Actualice la pantalla.'
            page.locator('#precio-cotizacion-101').fill('680')
            page.get_by_role('button', name='Actualizar Precio', exact=True).click()
            page.locator('[data-action="confirm"]').click()
            page.get_by_text(state['price_error'], exact=True).wait_for(timeout=3000)
        def api_json(page, state):
            page.evaluate('async () => { await API.rechazarPedido(101); await API.aceptarCotizacion(101); }')
            assert len(state['posts']) == 2
            assert all(r.post_data_json == {} for r in state['posts'])
        def remote_accept(page, state):
            state['quotes'][0]['estado'] = 'Aceptada'
            refresh(page)
            page.locator('[data-quote-id="101"] .modal-badge').get_by_text('Aceptada', exact=True).wait_for(timeout=1500)
            assert page.get_by_role('button', name='Actualizar Precio', exact=True).count() == 0
            assert page.get_by_role('button', name='Rechazar', exact=True).count() == 0
            assert page.get_by_role('button', name='Pasar a Caja', exact=True).is_visible()
            assert page.locator('#pedidos-clientes-modal').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
            output = ROOT / 'scratch/pos-quotes'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f'accepted-{page.viewport_size["width"]}.png'), full_page=True)
        def draft(page, state):
            page.locator('#precio-cotizacion-101').fill('711')
            refresh(page)
            assert page.locator('#precio-cotizacion-101').input_value() == '711'
        def remote_price(page, state):
            state['quotes'][0]['precio_cotizado'] = 725
            refresh(page)
            assert page.locator('#precio-cotizacion-101').input_value() == '725.00'
        for name, check in [('Actualizar precio', update), ('Rechazar', rejected),
                            ('Error descriptivo', invalid_price), ('JSON aceptar/rechazar', api_json),
                            ('Aceptación WhatsApp actualiza POS', remote_accept),
                            ('Precio remoto actualiza POS', remote_price), ('Borrador sin cambios remotos', draft)]:
            case(name, check)
        case('Aceptación WhatsApp móvil', remote_accept, width=390)
        browser.close()
    if errors:
        raise SystemExit(f'{len(errors)} comprobaciones fallidas')


if __name__ == '__main__':
    run()
