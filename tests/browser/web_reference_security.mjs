/** Current production scripts, synthetic API responses; all network is intercepted. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
const require = createRequire('C:/Users/miure/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium} = require('playwright');
const root = process.cwd(), out = path.join(root, 'scratch/remediation_20261020/web');
const posHTML = execFileSync(process.env.WEB_TEST_PYTHON || path.join(root, 'scratch/remediation_20261017/venv/Scripts/python.exe'),
    ['tests/browser/render_web_reference_fixture.py'], {encoding: 'utf8'});
const payload = 'x"><img src="data:image/png;base64,invalid" onerror="window.__quoteXSS=true">';
const references = [payload, 'javascript:alert(1)', 'https://evil.example/photo.png',
    'uploads/referencias/design.png', 'https://i.ibb.co/Ab12Cd/design.png'];
const quotes = references.map((ruta_imagen, i) => ({id: 701 + i, cliente: 'Synthetic Guest',
    telefono: '88887777', fecha_entrega: '2026-12-01', estado: 'Pendiente',
    especificaciones: 'Synthetic request', ruta_imagen, precio_cotizado: null}));
const browser = await chromium.launch({channel: 'msedge', headless: true, args: ['--disable-gpu']});
const results = [];
async function test(name, fn) {
    const page = await browser.newPage();
    try { await fn(page); results.push({name, passed: true}); console.log('PASS ' + name); }
    catch (error) { results.push({name, passed: false, error: error.message}); console.error('FAIL ' + name + ': ' + error.message); }
    finally { await page.close(); }
}
try {
    await test('Stored quote image cannot inject markup or unsafe navigation', async page => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'security.audit') return route.abort();
            if (url.pathname === '/pos') return route.fulfill({contentType: 'text/html',
                headers: {'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; connect-src 'self';"},
                body: posHTML
                    .replace('</body>', '<button id="btn-pedidos-clientes">Alternate requests</button></body>')});
            if (url.pathname === '/api/cotizaciones/pendientes' || url.pathname === '/api/cotizaciones/cliente') return route.fulfill({json: quotes});
            if (url.pathname === '/admin/api/tipo_cambio') return route.fulfill({json: {tipo_cambio: 36.6}});
            if (url.pathname.startsWith('/static/')) {
                const target = path.resolve(root, '.' + url.pathname);
                if (!target.startsWith(path.join(root, 'static') + path.sep)) return route.abort();
                try { return await route.fulfill({path: target}); } catch { return route.abort(); }
            }
            return route.fulfill({status: 404, body: ''});
        });
        await page.addInitScript(() => { window.__quoteXSS = false; });
        await page.goto('http://security.audit/pos');
        await page.locator('#btn-ver-pedidos-clientes').click();
        await page.waitForFunction(() => document.querySelectorAll('#cotizaciones-pendientes-list .modal-section').length === 5);
        assert.equal(await page.locator('#cotizaciones-pendientes-list img[onerror]').count(), 0);
        assert.equal(await page.evaluate(() => window.__quoteXSS), false);
        const links = page.locator('#cotizaciones-pendientes-list a');
        assert.deepEqual(await links.evaluateAll(nodes => nodes.map(node => node.getAttribute('href'))), [
            '/static/uploads/referencias/design.png', 'https://i.ibb.co/Ab12Cd/design.png']);
        assert.ok((await links.evaluateAll(nodes => nodes.map(node => node.rel))).every(rel => rel.includes('noopener') && rel.includes('noreferrer')));
        await page.evaluate(() => document.querySelector('#btn-mis-cotizaciones').click());
        await page.waitForFunction(() => document.querySelectorAll('#cotizaciones-cliente-list .sales-ui-text-7').length === 5);
        assert.deepEqual(await page.locator('#cotizaciones-cliente-list a').evaluateAll(nodes => nodes.map(node => node.getAttribute('href'))), [
            '/static/uploads/referencias/design.png', 'https://i.ibb.co/Ab12Cd/design.png']);
        await page.evaluate(() => document.querySelector('#btn-pedidos-clientes').click());
        await page.waitForFunction(() => document.querySelectorAll('#cotizaciones-pendientes-list .sales-ui-text-17').length === 5);
        assert.deepEqual(await page.locator('#cotizaciones-pendientes-list .sales-ui-btn-7').evaluateAll(nodes => nodes.map(node => node.getAttribute('href'))), [
            '/static/uploads/referencias/design.png', 'https://i.ibb.co/Ab12Cd/design.png']);
        assert.deepEqual(errors, []);
    });
    await test('Error panel renders actual API fields as text', async page => {
        const source = await fs.readFile(path.join(root, 'templates/admin/configuracion.html'), 'utf8');
        const script = source.split('{% block extra_scripts %}')[1].split('<script>')[1].split('</script>')[0];
        const record = {id: 999, fecha_hora: '20/10/2026', origen: 'SQL_SP', severidad: 'ERROR',
            procedimiento: 'synthetic.procedure', mensaje: 'SYNTHETIC_MESSAGE <img src=x onerror="window.__panelXSS=true">',
            usuario: 'SYNTHETIC_USER <b>literal</b>', rol: 'Estandar', notificado_smtp: false};
        await page.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'security.audit') return route.abort();
            if (url.pathname === '/panel') return route.fulfill({contentType: 'text/html', body:
                `<meta charset="utf-8"><table><tbody id="tbody-bitacora-errores"></tbody></table><script>${script}</script>`});
            if (url.pathname === '/admin/api/seguridad/bitacora-errores') return route.fulfill({json: {success: true, errores: [record]}});
            return route.abort();
        });
        await page.goto('http://security.audit/panel');
        await page.evaluate(() => cargarBitacoraErrores());
        const cells = await page.locator('#tbody-bitacora-errores td').allTextContents();
        assert.equal(cells[4], record.usuario + ' (Estandar)');
        assert.equal(cells[5], record.mensaje);
        assert.equal(await page.locator('#tbody-bitacora-errores img, #tbody-bitacora-errores b').count(), 0);
        assert.equal(await page.evaluate(() => Boolean(window.__panelXSS)), false);
        assert.equal(cells[6], '⏳ Pendiente');
    });
} finally {
    await browser.close();
    await fs.mkdir(out, {recursive: true});
    await fs.writeFile(path.join(out, 'browser-results.json'), JSON.stringify(results, null, 2));
}
if (results.some(result => !result.passed)) process.exitCode = 1;
