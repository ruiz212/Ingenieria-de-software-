/** Read-only navigation regression checks against an explicit local QA server.
 * CSS viewport pixels and device pixels are tested separately. No business writes.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(process.env.PLAYWRIGHT_MODULES ? path.join(process.env.PLAYWRIGHT_MODULES,'package.json') : import.meta.url);
const {chromium}=require('playwright');
const base=process.env.WEB_UI_BASE_URL;
assert.match(base||'',/^http:\/\/127\.0\.0\.1:\d+$/,'Supply the isolated local QA server');
const access=JSON.parse(await fs.readFile(process.env.WEB_UI_ACCESS_FILE,'utf8'));
const output=process.env.WEB_UI_OUTPUT||'scratch/navigation_layout';
const phase=process.env.NAVIGATION_PHASE||'all';
assert.ok(['all','matrix','no-js'].includes(phase),'NAVIGATION_PHASE must be all, matrix or no-js');
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors=[];const results=[];
const visibleInViewport=async(locator,label)=>{
 const result=await locator.evaluate(el=>{
  const r=el.getBoundingClientRect(),style=getComputedStyle(el);
  const x=r.x+r.width/2,y=r.y+r.height/2;
  return {x:r.x,y:r.y,width:r.width,height:r.height,viewportWidth:innerWidth,viewportHeight:innerHeight,
   rendered:style.display!=='none'&&style.visibility==='visible',inert:!!el.closest('[inert]'),
   hit:el.contains(document.elementFromPoint(x,y))};
 });
 assert.ok(result.rendered&&!result.inert&&result.width>0&&result.height>0,`${label}: rendered and active ${JSON.stringify(result)}`);
 assert.ok(result.x>=0&&result.y>=0&&result.x+result.width<=result.viewportWidth+1&&result.y+result.height<=result.viewportHeight+1,`${label}: inside viewport ${JSON.stringify(result)}`);
 assert.ok(result.hit,`${label}: reachable by pointer ${JSON.stringify(result)}`);
 return result;
};
try{
 const login=await browser.newContext({reducedMotion:'reduce'});
 const loginPage=await login.newPage();
 await loginPage.goto(`${base}/login`);
 await loginPage.locator('[name="identificador"]').fill(access.usuario);
 await loginPage.locator('[name="password"]').fill(access.clave);
 await loginPage.locator('button[type="submit"]').click();
 await loginPage.waitForURL(url=>!url.pathname.includes('/login'));
 const storageState=await login.storageState();await login.close();
 for(const deviceScaleFactor of (phase==='no-js'?[]:[1,1.25,2]))for(const theme of ['light','dark']){
  const context=await browser.newContext({storageState,viewport:{width:1440,height:688},deviceScaleFactor,reducedMotion:'reduce'});
  await context.addInitScript(theme=>localStorage.setItem('theme',theme),theme);
  const page=await context.newPage();page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/static/')&&r.status()>=400)errors.push(`${r.status()} ${r.url()}`);});
  for(const route of ['/admin/dashboard','/monitor']){
   const response=await page.goto(base+route);assert.equal(response.status(),200,route);
   await page.waitForFunction(()=>document.documentElement.classList.contains('has-navigation-js'));
   assert.ok(await page.locator('link[rel="stylesheet"][href*="/static/"]').evaluateAll(links=>links.every(el=>!!el.sheet)),`${route}: local stylesheets loaded`);
   for(const width of [390,768,899,900,901,1024,1272,1440,1600]){
    await page.setViewportSize({width,height:688});
    const label=`${route} ${width}px DPR${deviceScaleFactor} ${theme}`;
    const nav=page.locator('#glass-dock'),toggle=page.locator('.mobile-menu-toggle');
    if(width<=900){
     await visibleInViewport(toggle,`${label} menu button`);
     assert.equal(await nav.evaluate(el=>el.inert),true,`${label}: closed drawer inert`);
     await toggle.click();
     await visibleInViewport(nav,`${label} open navigation`);
     await visibleInViewport(nav.locator('.dock-footer a'),`${label} logout`);
     assert.equal(await toggle.getAttribute('aria-expanded'),'true');
     const monitor=nav.getByRole('link',{name:'Monitor',exact:true});await monitor.scrollIntoViewIfNeeded();
     await visibleInViewport(monitor,`${label} monitor link`);
     await monitor.click();await page.waitForURL(url=>url.pathname==='/monitor');
     assert.equal(await page.locator('.mobile-menu-toggle').getAttribute('aria-expanded'),'false',`${label}: navigation closes on route change`);
     // Return to the page under test; loading a route must preserve an accessible entry.
     await page.goto(base+route);await visibleInViewport(page.locator('.mobile-menu-toggle'),`${label} after navigation`);
    }else{
     const bounds=await visibleInViewport(nav,`${label} persistent navigation`);
     const main=await page.locator('.main-content').boundingBox();
     assert.ok(main.x>=bounds.x+bounds.width,`${label}: content leaves space for navigation`);
     const search=page.getByLabel('Buscar sección');await visibleInViewport(search,`${label} navigation search`);
     await search.fill('monitor');const monitor=nav.getByRole('link',{name:'Monitor',exact:true});
     await visibleInViewport(monitor,`${label} filtered monitor link`);await monitor.click();
     await page.waitForURL(url=>url.pathname==='/monitor');await page.goto(base+route);
    }
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${label}: horizontal overflow`);
    results.push({route,width,deviceScaleFactor,theme});
    if(width===1272&&deviceScaleFactor===1.25&&theme==='dark')await page.screenshot({path:path.join(output,`${route.split('/').pop()}-1272-dpr125-dark.png`),animations:'disabled'});
   }
  }
  // An open mobile drawer must release the main region on a desktop resize.
  await page.setViewportSize({width:390,height:688});await page.locator('.mobile-menu-toggle').click();
  await page.setViewportSize({width:901,height:688});await visibleInViewport(page.locator('#glass-dock'),'mobile-open to desktop');
  assert.equal(await page.locator('.main-content').evaluate(el=>el.inert),false);
  await context.close();
 }
 for(const width of (phase==='matrix'?[]:[390,901])){
  const context=await browser.newContext({storageState,javaScriptEnabled:false,viewport:{width,height:688}});
  const page=await context.newPage();await page.goto(base+'/admin/dashboard');
  assert.equal(await page.locator('html').getAttribute('class'),null,'Navigation fallback must run with JavaScript disabled');
  const link=page.locator('#glass-dock').getByRole('link',{name:'Monitor',exact:true});
  await link.scrollIntoViewIfNeeded();await visibleInViewport(link,`No JavaScript ${width}px monitor link`);
  await link.click();await page.waitForURL(url=>url.pathname==='/monitor');
  results.push({javascript:false,width});await context.close();
 }
 assert.deepEqual(errors,[],'Runtime and static asset failures');
 await fs.writeFile(path.join(output,`navigation-${phase}-results.json`),JSON.stringify({results,errors},null,2));
 console.log(JSON.stringify({phase,cases:results.length,errors}));
}finally{await browser.close();}
