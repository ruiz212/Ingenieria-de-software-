/** Read-only UI checks against an explicitly supplied local QA server/account.
 * PLAYWRIGHT_MODULES: optional directory containing the playwright package.
 * WEB_UI_ACCESS_FILE: JSON with usuario and clave for an existing QA account.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require = createRequire(process.env.PLAYWRIGHT_MODULES
    ? path.join(process.env.PLAYWRIGHT_MODULES, 'package.json') : import.meta.url);
const {chromium} = require('playwright');
const base = process.env.WEB_UI_BASE_URL || 'http://127.0.0.1:5065';
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/, 'Use a local QA server');
const access = JSON.parse(await fs.readFile(process.env.WEB_UI_ACCESS_FILE, 'utf8'));
const output = process.env.WEB_UI_OUTPUT || 'scratch/web_ui';
await fs.mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu']});
const errors = [];
const results = [];
try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce',hasTouch:true});
    const page = await context.newPage();
    page.on('pageerror', error=>errors.push(`${page.url()}: ${error.stack}`));
    await page.goto(`${base}/login`);
    await page.locator('[name="identificador"]').fill(access.usuario);
    await page.locator('[name="password"]').fill(access.clave);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url=>!url.pathname.includes('/login'));
    await page.goto(`${base}/admin/dashboard`);
    const primary=page.getByRole('link',{name:'Ir al punto de venta',exact:false});
    const contrast=element=>{
        const style=getComputedStyle(element);
        const luminance=color=>{
            const values=color.match(/[\d.]+/g).slice(0,3).map(Number).map(value=>value/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);
            return values.reduce((total,value,index)=>total+value*[.2126,.7152,.0722][index],0);
        };
        const values=[luminance(style.color),luminance(style.backgroundColor)].sort((a,b)=>a-b);
        return (values[1]+.05)/(values[0]+.05);
    };
    assert.ok(await primary.evaluate(contrast)>=4.5,'Primary action contrast');
    await primary.hover();
    assert.ok(await primary.evaluate(contrast)>=4.5,'Primary action hover contrast');
    await page.setViewportSize({width:390,height:844});
    assert.ok((await page.locator('.topbar').boundingBox()).height<=100,'Mobile header must leave space for the task');
    const menu = page.locator('.mobile-menu-toggle');
    await menu.tap();
    const nav = page.locator('#glass-dock');
    assert.ok(await nav.evaluate(el=>el.offsetHeight>400), 'Mobile navigation must expose a full vertical menu');
    assert.ok(await nav.locator('.dock-footer').isVisible(), 'Logout must remain available on mobile');
    await page.screenshot({path:`${output}/menu-movil.png`,animations:'disabled',timeout:15000});
    await page.getByLabel('Buscar sección').fill('tributaria');
    assert.equal(await nav.locator('.dock-menu .dock-item:visible').count(),1);
    await page.getByLabel('Buscar sección').fill('no-existe-xyz');
    assert.ok(await page.getByText('No encontramos esa sección.').isVisible());
    await page.getByRole('button',{name:'Limpiar búsqueda'}).click();
    assert.ok(await nav.locator('.dock-menu .dock-item:visible').count()>8);
    await nav.locator('a').first().focus();
    await page.keyboard.press('Shift+Tab');
    assert.ok(await nav.getByRole('link',{name:'Salir',exact:true}).evaluate(element=>element===document.activeElement),'Mobile focus wraps inside the menu');
    await page.keyboard.press('Tab');
    assert.ok(await nav.locator('a').first().evaluate(element=>element===document.activeElement));
    await page.keyboard.press('Escape');
    assert.equal(await nav.evaluate(el=>el.inert),true);
    assert.equal(await menu.getAttribute('aria-expanded'),'false');
    assert.ok(await menu.evaluate(el=>el===document.activeElement));
    results.push('Mobile navigation: full menu, logout, search, empty result, Escape and focus');
    await page.setViewportSize({width:1440,height:1000});
    assert.equal(await nav.evaluate(el=>el.inert),false);
    await page.getByLabel('Buscar sección').fill('produccion');
    assert.equal(await nav.locator('.dock-menu .dock-item:visible').count(),1,'Search handles accented section names');
    await page.getByRole('button',{name:'Limpiar búsqueda'}).click();
    assert.ok(await page.getByRole('link',{name:'DGI / Gestión tributaria',exact:true}).isVisible());
    await page.evaluate(()=>{
        window.confirmationResult=null;
        window.showConfirm({title:'Comprobación de teclado',message:'Sin cambios en datos.'}).then(value=>window.confirmationResult=value);
    });
    const dialog = page.getByRole('dialog',{name:'Comprobación de teclado'});
    await dialog.waitFor();
    assert.ok(await dialog.getByRole('button',{name:'Cancelar',exact:true}).evaluate(el=>el===document.activeElement));
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>window.confirmationResult),false);
    results.push('Confirmation: semantic dialog, safe initial focus and Escape cancellation');
    assert.equal(await page.evaluate(()=>{
        const form=document.createElement('form');
        form.method='post';
        form.innerHTML='<button type="submit">Prueba</button>';
        form.addEventListener('submit',event=>event.preventDefault());
        document.body.append(form);
        form.requestSubmit();
        const busy=form.querySelector('button').dataset.submitting;
        form.remove();
        return busy;
    }),undefined,'Cancelled/AJAX submission must not activate native navigation lock');
    await page.goto(`${base}/admin/dgi/revisiones/${access.revision}`);
    for (const name of ['Descargar diagnóstico Excel','Descargar informe validado']) {
        const form=page.locator('form').filter({has:page.getByRole('button',{name,exact:true})});
        assert.notEqual(await form.getAttribute('data-download'),null,`${name}: explicit attachment contract`);
    }
    await page.route('**/__ui_attachment__',route=>route.fulfill({status:200,headers:{'content-type':'application/octet-stream','content-disposition':'attachment; filename="qa-ui.txt"'},body:'QA browser download test'}));
    await page.evaluate(()=>{
        const form=document.createElement('form');
        form.method='post'; form.action='/__ui_attachment__'; form.dataset.download='';
        form.innerHTML='<button type="submit">Prueba de descarga</button>';
        document.body.append(form);
    });
    for(let i=0;i<2;i++) {
        const received=page.waitForEvent('download');
        await page.getByRole('button',{name:'Prueba de descarga',exact:true}).click();
        await received;
        assert.notEqual(await page.getByRole('button',{name:'Prueba de descarga',exact:true}).getAttribute('data-submitting'),'true');
    }
    results.push('Submission: cancelled forms stay ready; attachment downloads can be repeated');
    for (const [name,route] of [['dashboard','/admin/dashboard'],['inventario','/admin/inventario'],['contabilidad','/admin/contabilidad'],['dgi','/admin/dgi'],['catalogo','/admin/catalogo'],['pos','/pos'],['monitor','/monitor']]) {
        const response=await page.goto(`${base}${route}`);
        assert.equal(response.status(),200,route);
        for (const width of [1440,768,390]) {
            await page.setViewportSize({width,height:1000});
            assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), `${route}: overflow at ${width}px`);
            if(width!==768)await page.screenshot({path:`${output}/${name}-${width}.png`,animations:'disabled',timeout:15000});
        }
    }
    await page.goto(`${base}/admin/dgi`);
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button',{name:'Activar tema oscuro'}).click();
    assert.ok(await page.locator('html').evaluate(el=>el.classList.contains('dark-theme')));
    await page.screenshot({path:`${output}/dgi-oscuro.png`,animations:'disabled',timeout:15000});
    results.push('Seven operating sections at 1440, 768 and 390 pixels; theme switch');
    const publicPage = await context.newPage();
    publicPage.on('pageerror',error=>errors.push(String(error)));
    await context.clearCookies();
    await publicPage.goto(`${base}/login`);
    await publicPage.getByLabel('Usuario o teléfono').fill('qa-usuario-inexistente-ui');
    await publicPage.getByLabel('Contraseña',{exact:true}).fill('incorrecta-solo-prueba-local');
    await publicPage.getByRole('button',{name:'Iniciar sesión',exact:true}).click();
    await publicPage.getByRole('alert').filter({hasText:'incorrectos'}).waitFor();
    await publicPage.getByRole('button',{name:'Mostrar contraseña',exact:true}).click();
    assert.equal(await publicPage.locator('#password').getAttribute('type'),'text');
    assert.equal(await publicPage.getByRole('button',{name:'Ocultar contraseña',exact:true}).getAttribute('aria-pressed'),'true');
    for(const [name,route] of [['login','/login'],['clientes','/cliente/bienvenida']]) {
        await publicPage.goto(`${base}${route}`);
        for(const width of [1440,390]) {
            await publicPage.setViewportSize({width,height:844});
            assert.ok(await publicPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${route}: horizontal overflow`);
            await publicPage.screenshot({path:`${output}/${name}-${width}.png`,animations:'disabled',timeout:15000});
        }
    }
    await publicPage.goto(`${base}/login`);
    await publicPage.setViewportSize({width:390,height:400});
    const loginSubmit=publicPage.getByRole('button',{name:'Iniciar sesión',exact:true});
    await loginSubmit.scrollIntoViewIfNeeded();
    const position=await loginSubmit.boundingBox();
    assert.ok(position.y>=0 && position.y+position.height<=400,'Short login viewport must allow scrolling to submit');
    results.push('Login: persistent invalid-credential error, password visibility and public entry responsiveness');
    assert.deepEqual(errors,[],'JavaScript runtime errors');
    await fs.writeFile(`${output}/results.json`,JSON.stringify({results,errors},null,2));
    console.log(JSON.stringify({results,errors}));
} finally {await browser.close();}
