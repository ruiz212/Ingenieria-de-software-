/** Customer catalogue checks on a local QA instance; never submits an order. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require = createRequire(process.env.PLAYWRIGHT_MODULES
    ? path.join(process.env.PLAYWRIGHT_MODULES, 'package.json') : import.meta.url);
const {chromium} = require('playwright');
const base = process.env.WEB_UI_BASE_URL;
assert.match(base || '', /^http:\/\/127\.0\.0\.1:\d+$/, 'Supply a local QA server');
const output = process.env.WEB_UI_OUTPUT || 'scratch/store_ui';
await fs.mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors = [];
const blockedWrites = [];
try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    // The guest session is GET-only. Block unexpected business writes as well.
    await context.route(`${base}/**`, route => {
        if (!['GET','HEAD'].includes(route.request().method())) {
            blockedWrites.push(route.request().url());
            return route.abort();
        }
        return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/cliente/invitado`);
    await page.locator('.tienda-body').waitFor();
    const cards = page.locator('.store-product-card');
    assert.ok(await cards.count() > 0, 'QA must contain a customer catalogue');
    for (const width of [1440,768,390,320]) {
        await page.setViewportSize({width,height:1000});
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Store overflow at ${width}`);
        for (const selector of ['#tienda-search-input','#btn-abrir-carrito-nav']) {
            const bounds = await page.locator(selector).boundingBox();
            assert.ok(bounds && bounds.x >= -1 && bounds.x + bounds.width <= width + 1, `${selector} clipped at ${width}`);
        }
        if ([1440,390].includes(width)) {
            await page.screenshot({path:`${output}/tienda-${width}.png`,animations:'disabled',timeout:15000});
        }
    }
    await page.setViewportSize({width:390,height:844});
    const search = page.locator('#tienda-search-input');
    await search.fill('sin-producto-qa-xyz');
    await page.waitForFunction(() => [...document.querySelectorAll('.store-product-card')].every(el => getComputedStyle(el).display === 'none'));
    await search.fill('');
    await cards.first().waitFor({state:'visible'});
    const category = page.locator('.category-btn[data-filter="Pan Salado"]');
    await category.click();
    assert.ok(await cards.filter({visible:true}).count() > 0);
    assert.ok(await cards.evaluateAll(elements => elements.filter(el => getComputedStyle(el).display !== 'none').every(el => el.dataset.categoria === 'Pan Salado')));
    const product = cards.filter({visible:true}).first();
    const name = await product.getAttribute('data-nombre');
    await product.getByRole('button', {name:`Agregar ${name}`,exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#badge-carrito-tienda').textContent === '1');
    await page.locator('#btn-abrir-carrito-nav').click();
    await page.locator('#cartDrawer.open').waitFor();
    assert.ok(await page.locator('#cart-items').getByText(name,{exact:true}).isVisible());
    assert.ok(await page.locator('#btn-realizar-pedido').isEnabled());
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({path:`${output}/tienda-carrito-390.png`,animations:'disabled',timeout:15000});
    await page.locator('#btn-cerrar-drawer-carrito').click();
    assert.equal(await page.locator('#cartDrawer').evaluate(el => el.classList.contains('open')), false);
    assert.deepEqual(blockedWrites, [], 'Catalogue and cart must remain read-only');
    assert.deepEqual(errors, []);
    const results = {results:['Catalogue at 1440, 768, 390 and 320 pixels','Search, category selection, add product, open and close cart; no order submitted'],errors,blockedWrites};
    await fs.writeFile(`${output}/store-results.json`, JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
} finally {
    await browser.close();
}
