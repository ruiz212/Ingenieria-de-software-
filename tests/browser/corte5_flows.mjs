/** Navegador real con respuestas sintéticas y sin acceso a red externa. */
import assert from 'node:assert/strict';
import path from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire('C:/Users/miure/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium} = require('playwright');
const root = process.cwd();
const browser = await chromium.launch({channel: 'msedge', headless: true, args: ['--disable-gpu']});

async function caseRun(name, fn) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try { await fn(page); console.log(`PASS ${name}`); }
  finally { await context.close(); }
}

try {
  await caseRun('DGI filters, paginates and prints unsafe customer text literally', async page => {
    const requests = [];
    const fixture = `<meta charset="utf-8"><section id="facturas-periodo" data-period="7" data-search-url="/admin/dgi/facturas">
      <input id="dgi-invoices-query"><select id="dgi-invoices-state"><option value=""></option><option>Emitida</option></select>
      <select id="dgi-invoices-type"><option value=""></option><option>Encargo</option></select>
      <input id="dgi-invoices-from"><input id="dgi-invoices-to"><select id="dgi-invoices-size"><option>10</option><option>25</option></select>
      <button id="dgi-invoices-refresh"></button><span id="dgi-invoices-status"></span><table><tbody id="dgi-invoices-body"></tbody></table>
      <button id="dgi-invoices-prev"></button><span id="dgi-invoices-page"></span><button id="dgi-invoices-next"></button></section>
      <script src="/static/js/dgi_invoices.js"></script>`;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'corte5.test') return route.abort();
      if (url.pathname === '/') return route.fulfill({contentType: 'text/html', body: fixture});
      if (url.pathname === '/static/js/dgi_invoices.js') return route.fulfill({path: path.join(root, 'static/js/dgi_invoices.js')});
      if (url.pathname === '/admin/dgi/facturas') {
        requests.push(url.searchParams.toString());
        return route.fulfill({json: {total: 26, facturas: [{id: 30, numero: 'FAC-00000030',
          fecha: '2026-10-21T09:00:00', cliente: '<img src=x onerror="window.__xss=true">',
          tipo: 'Encargo', estado: 'Emitida', total: '100.00', reciente: true}]}});
      }
      return route.abort();
    });
    await page.goto('http://corte5.test/');
    await page.waitForFunction(() => document.querySelector('#dgi-invoices-body tr'));
    assert.equal(await page.locator('#dgi-invoices-body img').count(), 0);
    assert.match(await page.locator('#dgi-invoices-body').innerText(), /<img src=x/);
    assert.equal(await page.locator('.dgi-invoice-recent').count(), 1);
    await page.locator('#dgi-invoices-query').fill('FAC-00000030');
    await page.locator('#dgi-invoices-size').selectOption('25');
    await page.waitForFunction(() => document.querySelector('#dgi-invoices-status').textContent.includes('26'));
    assert.ok(requests.some(value => value.includes('buscar=FAC-00000030') && value.includes('tamano=25')));
    await page.locator('#dgi-invoices-next').click();
    await page.waitForFunction(() => document.querySelector('#dgi-invoices-page').textContent.includes('Página 2'));
    assert.ok(requests.some(value => value.includes('pagina=2')));
  });

  await caseRun('Draft survives reload and clears after success', async page => {
    const fixture = `<meta charset="utf-8"><body data-draft-user="qa"><form data-draft-key="perfil-dgi"><input id="nombre"><textarea id="obligaciones"></textarea></form><script src="/static/js/form_drafts.js"></script></body>`;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'corte5.test') return route.abort();
      if (url.pathname === '/') return route.fulfill({contentType: 'text/html', body: fixture});
      if (url.pathname === '/static/js/form_drafts.js') return route.fulfill({path: path.join(root, 'static/js/form_drafts.js')});
      return route.abort();
    });
    await page.goto('http://corte5.test/');
    await page.locator('#nombre').fill('Perfil pendiente');
    await page.evaluate(() => window.removeEventListener('beforeunload', () => {}));
    page.once('dialog', dialog => dialog.accept());
    await page.reload();
    assert.equal(await page.locator('#nombre').inputValue(), 'Perfil pendiente');
    assert.match(await page.locator('.draft-restored-note').innerText(), /Borrador recuperado/);
    assert.equal(await page.evaluate(() => {
      const event = new Event('beforeunload', {cancelable: true});
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }), true);
    await page.evaluate(() => window.clearFormDraft(document.querySelector('form')));
    assert.equal(await page.evaluate(() => sessionStorage.length), 0);
  });

  await caseRun('Warning renews with current CSRF token only on button press', async page => {
    const methods = [];
    const fixture = `<meta name="csrf-token" content="old"><body data-session-guard><script src="/static/js/common.js"></script><script src="/static/js/session_guard.js"></script></body>`;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'corte5.test') return route.abort();
      if (url.pathname === '/') return route.fulfill({contentType: 'text/html', body: fixture});
      if (url.pathname === '/static/js/common.js') return route.fulfill({path: path.join(root, 'static/js/common.js')});
      if (url.pathname === '/static/js/session_guard.js') return route.fulfill({path: path.join(root, 'static/js/session_guard.js')});
      if (url.pathname === '/auth/ping') {
        methods.push({method: route.request().method(), token: route.request().headers()['x-csrftoken']});
        return route.fulfill({json: {expires_in_seconds: route.request().method() === 'POST' ? 600 : 100,
          csrf_token: 'fresh'}});
      }
      return route.abort();
    });
    await page.goto('http://corte5.test/');
    await page.locator('.session-guard-dialog[open]').waitFor();
    assert.deepEqual(methods.map(row => row.method), ['GET']);
    await page.locator('[data-session-continue]').click();
    await page.waitForFunction(() => !document.querySelector('.session-guard-dialog').open);
    assert.deepEqual(methods, [{method: 'GET', token: undefined}, {method: 'POST', token: 'fresh'}]);
  });
} finally { await browser.close(); }
