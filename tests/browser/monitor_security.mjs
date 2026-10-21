/** Actual card renderer, hostile values, real DOM; no server or business writes. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/miure/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium}=require('playwright');
const source=await fs.readFile('static/js/features/monitor-card.js','utf8');
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
try {
 const page=await browser.newPage();
 await page.goto('about:blank');
 await page.addScriptTag({content:source});
 const result=await page.evaluate(async()=>{
  const payload='<img src="data:image/png;base64,invalid" onerror="window.__monitorXSS=true">';
  window.__monitorXSS=false;window.clicked=[];
  window.cambiarEstado=(...args)=>window.clicked.push(args);
  const code="synthetic');window.__monitorXSS=true;//";
  const card=createCard({codigo_seguimiento:code,numero_factura:payload,productos:[{nombre:payload,cantidad:1,detalle_ingredientes:{ingredientes:[{nombre:payload}]}}],encargo_detalles:{estado:'Pendiente',nombre_cliente:payload,notas:payload,especificaciones:payload,ruta_imagen_referencia:'javascript:window.__monitorXSS=true',telefono:payload}});
  document.body.append(card);
  await new Promise(resolve=>setTimeout(resolve,100));
  const scriptExecuted=window.__monitorXSS;
  const unsafeImageCount=card.querySelectorAll('img').length;
  const inlineHandlers=card.querySelectorAll('[onclick],[onerror]').length;
  const textPreserved=card.textContent.includes(payload);
  card.querySelector('button').click();
  const clicked=window.clicked;
  return {scriptExecuted,unsafeImageCount,inlineHandlers,textPreserved,clicked,code};
 });
 assert.equal(result.scriptExecuted,false,'User strings must remain text');
 assert.equal(result.unsafeImageCount,0,'Invalid image protocols must be rejected');
 assert.equal(result.inlineHandlers,0,'Untrusted codes must never enter executable attributes');
 assert.equal(result.textPreserved,true,'Notes must retain their literal content');
 assert.deepEqual(result.clicked,[[result.code,'En Proceso']]);
 console.log(JSON.stringify({monitorSecurity:'passed',checks:5,businessWrites:false}));
} finally {await browser.close();}
