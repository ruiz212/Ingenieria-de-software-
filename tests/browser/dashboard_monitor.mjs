/** Read-only agreement between the rendered dashboard and the live kitchen API. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(process.env.PLAYWRIGHT_MODULES
    ? path.join(process.env.PLAYWRIGHT_MODULES,'package.json') : import.meta.url);
const {chromium}=require('playwright');
const base=process.env.WEB_UI_BASE_URL;
assert.match(base||'',/^http:\/\/127\.0\.0\.1:\d+$/);
const access=JSON.parse(await fs.readFile(process.env.WEB_UI_ACCESS_FILE,'utf8'));
const output=process.env.WEB_UI_OUTPUT||'scratch/dashboard_monitor';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
try {
    const context=await browser.newContext({viewport:{width:1280,height:692},deviceScaleFactor:1.25,reducedMotion:'reduce'});
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`${base}/login`);
    await page.locator('[name="identificador"]').fill(access.usuario);
    await page.locator('[name="password"]').fill(access.clave);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url=>!url.pathname.includes('/login'));
    await context.route(`${base}/**`,route=>['GET','HEAD'].includes(route.request().method())?route.continue():route.abort());
    await page.evaluate(()=>localStorage.setItem('theme','dark'));
    const response=await page.goto(`${base}/admin/dashboard`);
    assert.equal(response.status(),200);
    const api=await page.request.get(`${base}/api/monitor/pedidos`);
    assert.equal(api.status(),200);
    const {encargos}=await api.json();
    assert.ok(Array.isArray(encargos));
    const metric=page.locator('.dashboard-metric').filter({has:page.getByText('Encargos por entregar',{exact:true})});
    assert.equal(Number(await metric.locator('.dashboard-metric-value').innerText()),encargos.length,'Dashboard and kitchen must count the same active backlog');
    const ready=encargos.filter(order=>order.encargo_detalles.estado==='Listo').length;
    assert.match(await metric.locator('.dashboard-metric-detail').first().innerText(),new RegExp(`^${ready} listo(?:s)? · `));
    assert.ok(await metric.getByText('Todos los días',{exact:false}).isVisible());
    await page.screenshot({path:`${output}/dashboard-dark-1280.png`,animations:'disabled'});
    await metric.getByRole('link',{name:'Ver monitor',exact:true}).click();
    await page.waitForURL(`${base}/monitor`);
    let boardCount=0;
    for (const state of ['Pendiente','En_Proceso','Listo']) boardCount+=Number(await page.locator(`#count-${state}`).innerText());
    assert.equal(boardCount,encargos.length,'Dashboard link opens the same kitchen backlog');
    await page.screenshot({path:`${output}/monitor-dark-1280.png`,animations:'disabled'});
    assert.deepEqual(errors,[]);
    const result={backlog:encargos.length,ready,boardCount,errors,businessWrites:false};
    await fs.writeFile(`${output}/dashboard-monitor-results.json`,JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
} finally {await browser.close();}
