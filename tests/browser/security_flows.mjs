import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/miure/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium}=require('playwright');
const base=process.env.WEB_UI_BASE_URL;
assert.match(base||'',/^http:\/\/127\.0\.0\.1:\d+$/);
const output=process.env.WEB_UI_OUTPUT||'scratch/remediation_20261017/browser';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors=[];const results=[];
try {
 const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 let sends=0;
 await page.route(`${base}/api/enviar_codigo_sms`,async route=>{
  assert.ok(route.request().headers()['x-csrftoken']);
  sends++;
  await route.fulfill({status:sends===1?200:429,json:sends===1?{mensaje:'Código de prueba enviado'}:{error:'Espera 60 segundos'}});
 });
 await page.route(`${base}/api/verificar_codigo_sms`,route=>route.fulfill({json:{mensaje:'Teléfono verificado'}}));
 await page.goto(`${base}/cliente/registro`);
 assert.equal(await page.locator('#step-2').isVisible(),false,'Only the active registration step should be visible');
 await page.locator('#nombre').fill('Synthetic');await page.locator('#apellidos').fill('QA');
 await page.getByRole('button',{name:'Continuar',exact:true}).filter({visible:true}).click();
 await page.locator('#genero').selectOption('Otro');await page.locator('#fecha_nacimiento').fill('2000-01-01');
 await page.getByRole('button',{name:'Continuar',exact:true}).filter({visible:true}).click();
 await page.locator('#telefono').fill('88887777');
 assert.ok(await page.locator('#btn-submit').isDisabled());
 await page.locator('#send-sms').click();await page.getByText('Código de prueba enviado',{exact:true}).waitFor();
 await page.locator('#send-sms').click();await page.getByText('Espera 60 segundos',{exact:true}).waitFor();
 assert.ok(await page.locator('#verify-sms').isEnabled(),'Rate-limited resend must preserve verification of the existing code');
 await page.locator('#sms-code').fill('123456');await page.locator('#verify-sms').click();
 await page.getByText('Teléfono verificado',{exact:true}).waitFor();
 assert.ok(await page.locator('#btn-submit').isEnabled());
 await page.locator('#telefono').fill('88886666');
 assert.ok(await page.locator('#btn-submit').isDisabled());
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:`${output}/registro-seguro-390.png`,animations:'disabled'});
 results.push('Registration SMS controls: CSRF, resend throttle, verification, changed phone; API responses mocked, no SMS/account created');
 await context.close();

 const kiosk=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
 await kiosk.addInitScript(()=>{
  navigator.mediaDevices.getUserMedia=async()=>{
   const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
   canvas.getContext('2d').fillRect(0,0,640,480);
   return canvas.captureStream(2);
  };
 });
 const kp=await kiosk.newPage();kp.on('pageerror',e=>errors.push(e.message));
 const marks=[];
 await kp.route(`${base}/kiosco/api/kiosco/reconocer`,route=>{
  marks.push(route.request().postDataJSON().accion);
  return route.fulfill({json:{status:'success',tipo:marks.at(-1),mensaje:'Marca sintética confirmada'}});
 });
 await kp.goto(`${base}/kiosco/`);
 await kp.getByText('IA lista — Selecciona entrada o salida',{exact:true}).waitFor();
 await kp.waitForTimeout(1100);assert.deepEqual(marks,[]);
 await kp.locator('#markEntry').click();await kp.waitForFunction(()=>document.body.textContent.includes('Marca sintética confirmada'));
 await kp.waitForTimeout(1600);assert.deepEqual(marks,['entrada']);
 await kp.screenshot({path:`${output}/kiosco-seguro-390.png`,animations:'disabled'});
 results.push('Kiosk: synthetic camera, no mark until selection, exactly one entry then persistent pause; no attendance written');
 await kiosk.close();

 const guest=await browser.newContext();const gp=await guest.newPage();
 await gp.goto(`${base}/cliente/invitado`);
 assert.equal((await gp.request.get(`${base}/api/monitor/pedidos`)).status(),403);
 const token=await gp.locator('meta[name="csrf-token"]').getAttribute('content');
 assert.equal((await gp.request.put(`${base}/api/seguimiento/SYNTHETIC/estado`,{data:{estado:'Entregado'},headers:{'X-CSRFToken':token}})).status(),403);
 results.push('Actual public guest session cannot read or update internal orders');
 await guest.close();
 assert.deepEqual(errors,[]);
 await fs.writeFile(`${output}/security-flows-results.json`,JSON.stringify({results,errors},null,2));
 console.log(JSON.stringify({results,errors}));
} finally {await browser.close();}
