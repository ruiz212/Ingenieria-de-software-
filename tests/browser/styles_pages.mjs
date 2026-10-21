/** Read-only coverage of the pages whose embedded presentation was extracted. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(process.env.PLAYWRIGHT_MODULES ? path.join(process.env.PLAYWRIGHT_MODULES,'package.json') : import.meta.url);
const {chromium}=require('playwright');
const base=process.env.WEB_UI_BASE_URL;
assert.match(base||'',/^http:\/\/127\.0\.0\.1:\d+$/);
const access=JSON.parse(await fs.readFile(process.env.WEB_UI_ACCESS_FILE,'utf8'));
const output=process.env.WEB_UI_OUTPUT||'scratch/styles_pages';await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors=[];const results=[];
try {
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const page=await context.newPage();page.setDefaultTimeout(15000);
 page.on('pageerror',error=>errors.push(`${page.url()}: ${error.message}`));
 page.on('response',r=>{if(r.url().includes('/static/css/')&&r.status()>=400)errors.push(`CSS ${r.status()}: ${r.url()}`);});
 await page.goto(`${base}/login`);await page.locator('[name="identificador"]').fill(access.usuario);await page.locator('[name="password"]').fill(access.clave);await page.locator('button[type="submit"]').click();await page.waitForURL(url=>!url.pathname.includes('/login'));
 await context.route(`${base}/**`,route=>['GET','HEAD'].includes(route.request().method())?route.continue():route.abort());
 for(const route of ['/admin/rrhh','/admin/rrhh/asistencia','/admin/arqueos','/admin/configuracion','/admin/usuarios','/admin/auditoria','/admin/produccion','/admin/estadistica','/admin/contabilidad/catalogo','/admin/contabilidad/comprobacion','/admin/contabilidad/mayor','/admin/contabilidad/balance','/admin/contabilidad/estado-resultados']){
  const response=await page.goto(`${base}${route}`);assert.equal(response.status(),200,route);
  assert.ok(await page.locator('main').isVisible(),route);
  assert.equal(await page.locator('main').count(),1,'One main landmark per page');
  const sheets=await page.locator('link[rel="stylesheet"][href*="/static/css/"]').evaluateAll(els=>els.map(el=>({url:el.href,loaded:Boolean(el.sheet)})));
  assert.ok(sheets.length>=4&&sheets.every(sheet=>sheet.loaded),JSON.stringify({route,sheets}));
  if(['/admin/rrhh','/admin/contabilidad/catalogo','/admin/contabilidad/comprobacion','/admin/contabilidad/mayor'].includes(route)){
   await page.screenshot({path:`${output}/${route.split('/').pop()}-1440.png`,animations:'disabled',timeout:15000});
   await page.setViewportSize({width:390,height:844});
   assert.ok(await page.locator('.mobile-menu-toggle').isVisible());
   if(route==='/admin/rrhh') {
    assert.ok(await page.locator('.rrhh-actions .btn').evaluateAll(buttons=>buttons.every(el=>el.scrollWidth<=el.clientWidth+1)), 'HR action labels must not be clipped');
   }
   await page.screenshot({path:`${output}/${route.split('/').pop()}-390.png`,animations:'disabled',timeout:15000});
   await page.setViewportSize({width:1440,height:1000});
  }
  results.push(route);
 }
 for(const route of ['/admin/contabilidad/balance?print=1','/admin/contabilidad/estado-resultados?print=1&mes=10&anio=2026']){
  const response=await page.goto(`${base}${route}`);assert.equal(response.status(),200,route);
  await page.emulateMedia({media:'print'});
  assert.deepEqual(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').map(a=>a.animationName)),[]);
  assert.ok(await page.locator('link[href*="/static/css/dist/print/"]').count()>0);
  await page.screenshot({path:`${output}/print-${route.includes('balance')?'balance':'resultados'}.png`,animations:'disabled',timeout:15000});
  await page.emulateMedia({media:'screen'});results.push(route);
 }
 await context.clearCookies();
 for(const route of ['/cliente/registro','/cliente/bienvenida','/seguimiento/CSS-QA-NO-EXISTE']){
  const response=await page.goto(`${base}${route}`);assert.equal(response.status(),200,route);
  assert.ok(await page.locator('body').isVisible());results.push(route);
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(`${output}/styles-pages-results.json`,JSON.stringify({results,errors},null,2));console.log(JSON.stringify({pages:results.length,errors}));
}finally{await browser.close();}
