/** Real monitor template, scripts and CSS; synthetic browser network only, no DB. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/miure/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium}=require('playwright');
const source=await fs.readFile('templates/monitor.html','utf8');
const renderer=await fs.readFile('static/js/features/monitor-card.js','utf8');
const sources=JSON.parse(await fs.readFile('static/css/sources.json','utf8'));
const css=(await Promise.all([...sources.app,...sources.accessibility,...sources.theme,...sources['pages/sales/monitor'],...sources.motion].map(path=>fs.readFile('static/css/'+path,'utf8')))).join('\n');
const order=(code,state='Pendiente')=>({codigo_seguimiento:code,numero_factura:'SYNTHETIC-'+code,productos:[{nombre:'Pastel',cantidad:1}],encargo_detalles:{estado:state,nombre_cliente:'Cliente sintético',especificaciones:'Detalle '.repeat(40),notas:'Nota '.repeat(40)}});
const initial=[order('A'),order('B','En Proceso')];
const content=source.match(/{% block content %}([\s\S]*?){% endblock %}/)[1].replace('{{ encargos|tojson|safe }}',JSON.stringify(initial));
const scripts=source.match(/{% block extra_scripts %}([\s\S]*?){% endblock %}/)[1].replace(/<script src="[^\n]+<\/script>/,`<script>${renderer}</script>`);
const html=`<!doctype html><html lang="es"><meta charset="utf-8"><meta name="csrf-token" content="synthetic"><style>${css}</style><body class="app-container page-monitor"><div class="main-content"><header class="topbar"><h1>Monitor</h1></header><main class="admin-layout">${content}</main></div><script>window.toasts=[];window.showToast=(...args)=>toasts.push(args);</script>${scripts}</body></html>`;
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
let failed=0,passed=0;
async function test(name,fn){if(process.argv[2]&&!name.includes(process.argv[2]))return;const page=await browser.newPage({viewport:{width:1280,height:600}});try{await page.route('https://kds.invalid/**',r=>r.fulfill({contentType:'text/html',body:html}));await page.goto('https://kds.invalid/monitor');await page.waitForLoadState('networkidle');await fn(page);passed++;console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+': '+e.message);}finally{await page.close();}}
try{
 for(const [name,status,body] of [['HTTP 500',500,{error:'synthetic'}],['HTTP 401',401,{error:'expired'}],['HTTP 403',403,{error:'forbidden'}],['missing array',200,{error:'synthetic'}],['invalid item',200,{encargos:[null]}],['invalid state',200,{encargos:[order('A','Unknown')]}],['invalid product',200,{encargos:[{...order('A'),productos:[null]}]}],['invalid note type',200,{encargos:[{...order('A'),encargo_detalles:{...order('A').encargo_detalles,notas:123}}]}]]){
  await test('Sync failure preserves orders: '+name,async page=>{
   await page.evaluate(async({status,body})=>{window.fetch=async()=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});await refrescarPedidos();},{status,body});
   assert.equal(await page.locator('.kds-card').count(),2,'Last confirmed orders must remain');
   assert.equal(await page.locator('.kds-sync-status').getAttribute('data-state'),'error','Failure must be visible, never synchronized');
  });
 }
 await test('Malformed JSON and network failure are visible',async page=>{
  for(const network of [false,true]){
   await page.evaluate(async network=>{window.fetch=async()=>{if(network)throw new TypeError('synthetic offline');return new Response('not json',{headers:{'Content-Type':'application/json'}});};await refrescarPedidos();},network);
   assert.equal(await page.locator('.kds-card').count(),2);assert.equal(await page.locator('.kds-sync-status').getAttribute('data-state'),'error');
  }
 });
 await test('Recovery accepts confirmed array including empty result',async page=>{
  await page.evaluate(async()=>{window.fetch=async()=>new Response(JSON.stringify({encargos:[]}));await refrescarPedidos();});
  assert.equal(await page.locator('.kds-card').count(),0);assert.equal(await page.locator('.kds-sync-status').getAttribute('data-state'),'synced');
 });
 await test('PUT failure during refresh keeps each confirmed state',async page=>{
  const states=await page.evaluate(async()=>{
   let finishPut;window.fetch=(url)=>url.includes('/estado')?new Promise(resolve=>finishPut=resolve):Promise.resolve(new Response(JSON.stringify({encargos:[encargos[1],encargos[0]]})));
   const change=cambiarEstado('A','En Proceso');await refrescarPedidos();finishPut(new Response(JSON.stringify({error:'synthetic refusal'}),{status:409}));await change;
   return encargos.map(e=>[e.codigo_seguimiento,e.encargo_detalles.estado]).sort();
  });assert.deepEqual(states,[['A','Pendiente'],['B','En Proceso']]);
 });
 await test('GET begun before PUT cannot overwrite its confirmation',async page=>{
  const states=await page.evaluate(async()=>{
   const stale=JSON.parse(JSON.stringify(encargos));let finishRead;window.fetch=url=>url.includes('/estado')?Promise.resolve(new Response(JSON.stringify({status:'success',nuevo_estado:'En Proceso'}))):new Promise(resolve=>finishRead=resolve);
   const read=refrescarPedidos();await cambiarEstado('A','En Proceso');finishRead(new Response(JSON.stringify({encargos:stale})));await read;return encargos.map(e=>[e.codigo_seguimiento,e.encargo_detalles.estado]);
  });assert.equal(states.find(e=>e[0]==='A')[1],'En Proceso');
 });
 await test('PUT requires success payload and rejects duplicate submissions',async page=>{
  const result=await page.evaluate(async()=>{let finishes=[],calls=0;window.fetch=()=>{calls++;return new Promise(resolve=>finishes.push(resolve));};const change=cambiarEstado('A','En Proceso');const disabled=document.querySelector('#card-A button')?.disabled;const duplicate=cambiarEstado('A','En Proceso');finishes.forEach(finish=>finish(new Response('{}')));await Promise.all([change,duplicate]);return {calls,disabled,state:encargos.find(e=>e.codigo_seguimiento==='A').encargo_detalles.estado,success:toasts.some(t=>!t[1])};});
  assert.deepEqual(result,{calls:1,disabled:true,state:'Pendiente',success:false});
 });
 await test('PUT HTTP, JSON, network and timeout errors never claim success',async page=>{
  const results=await page.evaluate(async()=>{
   const results=[];
   for(const status of [400,401,403,404,409,500]){
    toasts=[];window.fetch=async()=>new Response(JSON.stringify({error:'synthetic refusal'}),{status});await cambiarEstado('A','En Proceso');
    results.push({state:encargos.find(e=>e.codigo_seguimiento==='A').encargo_detalles.estado,success:toasts.some(t=>!t[1]),sync:document.querySelector('.kds-sync-status').dataset.state});
   }
   for(const invalidJSON of [false,true]){
    toasts=[];window.fetch=async()=>{if(!invalidJSON)throw new TypeError('synthetic offline');return new Response('invalid json');};await cambiarEstado('A','En Proceso');
    results.push({state:encargos.find(e=>e.codigo_seguimiento==='A').encargo_detalles.estado,success:toasts.some(t=>!t[1]),sync:document.querySelector('.kds-sync-status').dataset.state});
   }return results;
  });for(const result of results)assert.deepEqual(result,{state:'Pendiente',success:false,sync:'error'});
  await page.clock.install();await page.evaluate(()=>{window.fetch=(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('synthetic timeout','AbortError'))));window.timeoutChange=cambiarEstado('A','En Proceso');});
  await page.clock.fastForward(10001);await page.evaluate(()=>timeoutChange);
  assert.equal(await page.locator('#list-Pendiente #card-A').count(),1);assert.equal(await page.locator('.kds-sync-status').getAttribute('data-state'),'error');assert.equal(await page.locator('#card-A button').isEnabled(),true);
 });
 await test('Confirmed states move through preparation, ready and delivery',async page=>{
  await page.evaluate(()=>{window.fetch=async(url,options)=>new Response(JSON.stringify({status:'success',nuevo_estado:JSON.parse(options.body).estado}));});
  for(const [state,column] of [['En Proceso','En_Proceso'],['Pendiente','Pendiente'],['En Proceso','En_Proceso'],['Listo','Listo'],['En Proceso','En_Proceso'],['Listo','Listo']]){
   await page.evaluate(state=>cambiarEstado('A',state),state);assert.equal(await page.locator('#list-'+column+' #card-A').count(),1);
  }
  await page.evaluate(()=>cambiarEstado('A','Entregado'));assert.equal(await page.locator('#card-A').count(),0);
 });
 await test('Polling preserves keyboard focus and reading position',async page=>{
  const result=await page.evaluate(async()=>{const list=document.querySelector('#list-Pendiente');list.scrollTop=list.scrollHeight;list.querySelector('button').focus();const top=list.scrollTop;window.fetch=async()=>new Response(JSON.stringify({encargos}));await refrescarPedidos();return {before:top,after:list.scrollTop,button:document.activeElement.closest('.kds-card')?.id};});
  assert.equal(result.button,'card-A');assert.equal(result.after,result.before);
 });
 await test('Confirmed action keeps keyboard focus with the moved order',async page=>{
  await page.evaluate(()=>{window.finishChange=null;window.fetch=()=>new Promise(resolve=>finishChange=resolve);});
  const button=page.locator('#card-A .kds-state-button');await button.focus();await page.keyboard.press('Enter');
  await page.evaluate(()=>finishChange(new Response(JSON.stringify({status:'success',nuevo_estado:'En Proceso'}))));
  await page.waitForFunction(()=>document.querySelector('#list-En_Proceso #card-A')&&!document.querySelector('#card-A [disabled]'));
  assert.equal(await page.evaluate(()=>document.activeElement.closest('.kds-card')?.id),'card-A');
 });
 await test('Finishing PUT does not steal focus from search',async page=>{
  await page.evaluate(()=>{window.fetch=()=>new Promise(resolve=>window.finishChange=resolve);});
  await page.locator('#card-A .kds-state-button').focus();await page.keyboard.press('Enter');await page.locator('#kds-search').focus();
  await page.evaluate(()=>finishChange(new Response(JSON.stringify({status:'success',nuevo_estado:'En Proceso'}))));
  await page.waitForFunction(()=>document.querySelector('#list-En_Proceso #card-A')&&!document.querySelector('#card-A [disabled]'));
  assert.equal(await page.evaluate(()=>document.activeElement.id),'kds-search');
 });
 await test('Scroll region supports keyboard and wraps long content',async page=>{
  await page.evaluate(()=>{encargos[0].encargo_detalles.nombre_cliente='X'.repeat(180);renderBoard();});
  const list=page.locator('#list-Pendiente');assert.equal(await list.getAttribute('tabindex'),'0');await list.focus();await page.keyboard.press('End');await page.waitForTimeout(150);
  const result=await list.evaluate(e=>({top:e.scrollTop,width:e.clientWidth,scrollWidth:e.scrollWidth}));assert.ok(result.top>0,'Keyboard must reach content below');assert.ok(result.scrollWidth<=result.width+1,'Long words must wrap');
 });
 await test('Text at 200 percent leaves room to see the complete action',async page=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>document.documentElement.style.fontSize='200%');
  const button=page.locator('#card-A .kds-state-button');await button.focus();
  const bounds=await button.evaluate(e=>{const button=e.getBoundingClientRect(),list=e.closest('.kds-column-body').getBoundingClientRect(),status=e.closest('.kds-card').querySelector('.kds-status-line strong');return {buttonHeight:button.height,listHeight:list.height,textWidth:e.scrollWidth,width:e.clientWidth,statusWidth:status.clientWidth};});
  assert.ok(bounds.listHeight>=bounds.buttonHeight,'A complete action must fit inside the scroll region');
  assert.ok(bounds.textWidth<=bounds.width+1,'Action label must be fully readable without clipping');
  assert.ok(bounds.width>=300,'Large text needs a useful column width, rather than three cramped columns');
  assert.ok(bounds.statusWidth>=100,'The state must remain readable without letter-by-letter wrapping');
 });
}finally{await browser.close();}
console.log(JSON.stringify({passed,failed,businessWrites:false}));if(failed)process.exitCode=1;
