/** Real browser checks for normal/reduced motion and final usable states. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(process.env.PLAYWRIGHT_MODULES ? path.join(process.env.PLAYWRIGHT_MODULES,'package.json') : import.meta.url);
const {chromium}=require('playwright');
const base=process.env.WEB_UI_BASE_URL;
assert.match(base || '',/^http:\/\/127\.0\.0\.1:\d+$/);
const access=JSON.parse(await fs.readFile(process.env.WEB_UI_ACCESS_FILE,'utf8'));
const output=process.env.WEB_UI_OUTPUT || 'scratch/motion_ui';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors=[]; const results=[];
try {
 for (const reducedMotion of ['no-preference','reduce']) {
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion});
  const page=await context.newPage(); page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/static/css/') && r.status()>=400) errors.push(`CSS ${r.status()}: ${r.url()}`);});
  await page.goto(`${base}/login`);
  assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--motion-enter').trim()),'260ms');
  await page.locator('[name="identificador"]').fill(access.usuario);
  await page.locator('[name="password"]').fill(access.clave);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(url=>!url.pathname.includes('/login'));
  await page.goto(`${base}/admin/dashboard`);
  const intro=page.locator('.dashboard-intro');
  if(reducedMotion==='no-preference') assert.equal(await intro.evaluate(el=>getComputedStyle(el).animationName),'ui-enter');
  else assert.equal(await intro.evaluate(el=>getComputedStyle(el).animationName),'none');
  await page.locator('.mobile-menu-toggle').click();
  await page.locator('#glass-dock').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{}))));
  assert.equal(await page.locator('#glass-dock').evaluate(el=>el.inert),false);
  await page.keyboard.press('Escape');
  await page.locator('.mobile-menu-toggle').click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#glass-dock').evaluate(el=>el.inert),true);
  assert.ok(await page.locator('.mobile-menu-toggle').evaluate(el=>el===document.activeElement));
  await page.evaluate(()=>{window.motionConfirm=null;window.showConfirm({title:'Prueba de movimiento',message:'Sin operaciones de negocio.'}).then(v=>window.motionConfirm=v);});
  await page.getByRole('dialog').waitFor();
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>window.motionConfirm===false);
  const animations=await page.evaluate(()=>document.getAnimations().filter(a=>a.effect?.getTiming().iterations===Infinity).map(a=>a.animationName));
  assert.deepEqual(animations,[],'Idle dashboard must not pulse or float indefinitely');
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:`${output}/dashboard-motion-${reducedMotion}.png`,animations:'disabled',timeout:15000});
  await context.clearCookies();
  await page.goto(`${base}/cliente/invitado`);
  const drawer=page.locator('#cartDrawer');
  assert.equal(await drawer.evaluate(el=>getComputedStyle(el).visibility),'hidden');
  await page.locator('#btn-abrir-carrito-nav').click();
  await drawer.evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{}))));
  assert.equal(await drawer.evaluate(el=>getComputedStyle(el).visibility),'visible');
  const bounds=await drawer.boundingBox();
  assert.ok(bounds.x>=-1 && bounds.x+bounds.width<=1441,'Open drawer stays inside viewport');
  await page.keyboard.press('Escape');
  await drawer.evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{}))));
  assert.equal(await drawer.evaluate(el=>getComputedStyle(el).visibility),'hidden');
  assert.ok(await page.locator('#btn-abrir-carrito-nav').evaluate(el=>el===document.activeElement));
  if(reducedMotion==='reduce') {
   assert.deepEqual(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').map(a=>a.animationName)),[]);
  }
  results.push(`Motion ${reducedMotion}: usable dashboard, interrupted menu, confirmation, cart and focus`);
  await context.close();
 }
 assert.deepEqual(errors,[]);
 await fs.writeFile(`${output}/motion-results.json`,JSON.stringify({results,errors},null,2));
 console.log(JSON.stringify({results,errors}));
}finally{await browser.close();}
