# Auditoría de diseño — Brajher's Cake

Fecha: 31-10-2026. Alcance: 50 plantillas HTML y 71 hojas CSS fuente, con inspección detallada de las superficies principales y componentes compartidos. Revisión estática del código, capturas sintéticas en Chrome/Playwright, detector Impeccable, guías UI/UX Pro Max y Web Interface Guidelines; consulta textual independiente a Antigravity. No se modificó la interfaz.

## Identidad a preservar

- La base compartida define café `#6B3A2A`, dorado `#D4952B` y crema `#F5F0EA` en `static/css/base/_variables.css`, con tema oscuro y tipografía Playfair Display, Inter y Outfit. Conservar esa familia cromática, la calidez artesanal y la estructura reconocible de cada flujo.
- La tienda usa una variante editorial cálida propia (`static/css/pages/customer/store.css`), todavía relacionada con panadería. El POS y la administración comparten más tokens; el kiosco usa una paleta morada y fondo casi negro distinta.
- La navegación administrativa ya ofrece búsqueda de sección, enlace para saltar al contenido y menú móvil (`templates/admin_base.html`, `templates/admin/sidebar.html`). El monitor añade texto a los estados, no depende únicamente del color (`templates/monitor.html`). El kiosco ofrece dos acciones grandes de 48 px y estado `aria-pressed`.

## Mapa por superficie

| Superficie | Evidencia revisada | Evaluación y validación pendiente |
| --- | --- | --- |
| Acceso y registro | `templates/login.html`, `cliente_*.html`, CSS de `pages/auth/` | El acceso tiene etiquetas, autocomplete y alertas. Revisar registro/TOTP con teclado, errores y zoom en navegador. |
| Tienda y seguimiento | `templates/tienda.html`, `seguimiento.html`, CSS de `pages/customer/` | Identidad cálida propia. Tienda comprobada con cuatro productos sintéticos en escritorio/móvil; seguimiento, carrito y cotizaciones requieren estados renderizados. |
| POS | `templates/pos.html`, CSS de `pages/sales/pos.css` | A 390 px, cabecera superpuesta a filtros y búsqueda; clics bloqueados. También hay etiquetas no asociadas y texto blanco sobre dorado. Validar modales, foco y errores de pago. |
| Monitor | `templates/monitor.html`, CSS de `pages/sales/monitor.css` | Tres columnas con texto y color, estado de sincronización anunciado. Validar legibilidad a distancia, teclado, actualización y alturas de columnas. |
| Kiosco | `templates/kiosco.html`, CSS de `pages/kiosk/attendance.css` | Interacción de entrada/salida clara, pero el aspecto morado oscuro se separa de la marca. Validar cámara denegada, feedback accesible y altura móvil. |
| Administración | `templates/admin_base.html`, `templates/admin/*.html`, CSS de `pages/admin/` | Dashboard y navegación vistos en 390/1440 px; el menú móvil funciona con JavaScript. El tema oscuro cambia y actualiza `aria-pressed`. Revisar los demás módulos, tablas e impresión. |

## Evidencia visual sintética

Playwright 1.64.1 con Chrome local capturó acceso, tienda, POS, monitor, kiosco y dashboard a 390 y 1440 px. Las 12 páginas sirvieron HTML y todas sus hojas CSS cargaron; el ancho documental no excedió el viewport en esas capturas. Eso no demuestra que controles internos sean usables: el POS ilustra lo contrario. Se activó JavaScript para validar la navegación móvil administrativa y la tienda/POS; kiosco se observó sin activar cámara. Los datos de producto y usuario son ficticios, y las solicitudes SQL/SMTP estuvieron prohibidas en la generación de plantillas.

- [POS móvil](design_audit_2026-10-31/pos-mobile-js.png) y [POS escritorio](design_audit_2026-10-31/pos-desktop.png).
- [Tienda móvil](design_audit_2026-10-31/tienda-mobile-js.png) y [tienda escritorio](design_audit_2026-10-31/tienda-desktop.png).
- [Monitor móvil](design_audit_2026-10-31/monitor-mobile-js.png), [dashboard móvil](design_audit_2026-10-31/dashboard-mobile-js.png) y [dashboard oscuro](design_audit_2026-10-31/dashboard-dark-desktop.png).
- [Acceso móvil](design_audit_2026-10-31/login-mobile.png) y [kiosco móvil](design_audit_2026-10-31/kiosco-mobile.png).
- [Tienda: primera pantalla en escritorio](design_audit_2026-10-31/tienda-inspect-desktop-fold.jpg), [tableta](design_audit_2026-10-31/tienda-inspect-tablet-fold.jpg) y [móvil](design_audit_2026-10-31/tienda-inspect-mobile-fold.jpg); [mediciones del inspector](design_audit_2026-10-31/tienda-inspect-report.json). Estas capturas sí cargaron la fotografía remota del hero; las capturas Playwright aisladas de la red no la muestran.

## Hallazgos priorizados

1. **P1 — POS móvil con filtros y búsqueda tapados.** A 390 px, `.header-actions` ocupa `y=88–230`, `.category-tabs` `y=89–161` y la búsqueda `y=173–221`. Las acciones de cabecera se dibujan encima; Playwright agotó 1,5 s al intentar pulsar “Pan dulce” y la búsqueda. A 768 y 1024 px, el clic en categoría sí funcionó. El CSS fuente de POS solo tiene un breakpoint para otros controles (`static/css/pages/sales/pos.css:426`), y su layout conserva `height:100vh` y desbordamiento interno (`:2`, `:41`). Reordenar cabecera, filtros y panel de factura para ancho estrecho, conservando colores y funciones.
2. **P1 — Contraste de texto blanco sobre dorado.** `static/css/pages/sales/pos.css:644` usa `--primary-color` con `#fff`; `static/css/pages/customer/tracking.css:11` usa el mismo par en cabecera y `:157` en indicador. Con los tokens base, el contraste calculado es **2.58:1** para blanco sobre `#D4952B`, por debajo de 4.5:1 para texto normal. Dorado sobre crema: 2.28:1; café `#6B3A2A` sobre dorado: 3.59:1. Café profundo `#3B2218` sobre dorado: 5.70:1; café `#6B3A2A` sobre crema: 8.19:1. Corregir parejas de texto/fondo sin cambiar los colores de marca.
3. **P1 — Etiquetas no asociadas a campos de pago y encargo.** `templates/pos.html:231`, `:235`, `:241`, `:245`, `:251`, `:260`, `:270`, `:298`, `:299` y varios campos de cobro posteriores usan `<label>` sin `for` y separados del `<input>` o `<select>`. El texto visible puede no anunciarse como nombre del control. Vincular cada etiqueta y conservar contenido y orden.
4. **P2 — Aviso del kiosco sin región de anuncio.** `templates/kiosco.html:48` y `:100` escriben en `#toast`, que no es región viva; el estado de cámara `#statusText` también cambia sin rol de estado. Se debe verificar con lector de pantalla. **Corrección al hallazgo inicial:** `static/js/common.js:33` sí agrega `aria-live="polite"` a `#toast-container` en administración, POS y tienda, hecho confirmado en el DOM renderizado. Los errores de cobro todavía ameritan revisión de prioridad y asociación al campo, pero no se afirma ausencia de anuncio global.
5. **P2 — Identidad del kiosco desconectada de la marca.** `static/css/pages/kiosk/attendance.css:28` define morado `#8e44ad` y fondo `#080810`; `templates/kiosco.html:15` muestra “FaceID Access”. La captura confirma la divergencia respecto del sistema cálido. Definir una adaptación que mantenga alto contraste de cámara y marcaje, sin imponer automáticamente la estética del escritorio al kiosco.
6. **P2 — Ubicación actual de navegación incompleta para tecnología asistiva.** `templates/admin/sidebar.html:25` y enlaces siguientes usan clase `active` según ruta pero no `aria-current="page"`. El resaltado visible existe; su significado no se comunica programáticamente. Revisar rutas anidadas y los dos enlaces DGI antes de unificar el patrón.
7. **P2 — Kiosco con altura bloqueada.** `static/css/pages/kiosk/attendance.css:52` establece `height:100vh` y `overflow:hidden`; el breakpoint móvil solo ajusta cámara, reloj y aviso (`:369`). A 390×844 px la captura entra en pantalla; el riesgo de recorte a 200% de zoom o menor altura sigue pendiente.
8. **P2 — Texto pequeño y tira de filtros recortada en tienda móvil.** El inspector de la página pública midió texto base de 14,4 px, 16 bloques inferiores a 13 px y una fila que desborda horizontalmente a 390 px. En la captura móvil, la barra utilitaria y etiquetas de catálogo son difíciles de leer, y las categorías del extremo derecho quedan fuera de vista sin una indicación clara de desplazamiento. Mejorar escala tipográfica y señal de navegación de filtros, manteniendo la composición editorial y los colores actuales.

### Revisión específica de la tienda con Design Taste Frontend

El primer vistazo comunica panadería artesanal mediante tipografía, café y crema, y una fotografía de pan en el hero. La acción principal para cotizar aparece en la primera pantalla; la vitrina y los precios se entienden después. En móvil, la foto cae debajo del texto y conserva una composición propia, aunque el encabezado concentra demasiadas etiquetas pequeñas. El inspector registró 14 `FAIL` y 7 `WARN` de su estilo editorial estricto; incluye juicios contra la crema de marca, sombras, bordes, emoji y tipografía monoespaciada. Esas alertas son preferencias del skill, no órdenes de sustituir una identidad que el usuario pidió conservar. Se retienen como hallazgos prácticos los tamaños de texto y la fila lateral; la escasez de fotos de producto no se generaliza porque la prueba usó productos sintéticos sin imágenes.

## Consulta independiente de Antigravity

Antigravity recibió un resumen sanitizado y **no vio el repositorio ni las pantallas**. Priorizó contraste en usos del dorado, ergonomía táctil de POS/kiosco y doble codificación de estados de pedidos. Sus dos últimas recomendaciones son hipótesis para probar, no fallos confirmados. Ajustes tras cotejar el código: el kiosco es de **empleados**, no de clientes; sus botones principales ya miden 48 px; el monitor ya incluye nombres de estado. El contraste preciso es 2.58:1 blanco/dorado, 3.59:1 café/dorado y 8.19:1 café/crema, en vez de las aproximaciones de la consulta.

## Límites de la auditoría

- El detector Impeccable reportó 15 alertas (10 de jerarquía tipográfica y 5 de imágenes), pero no pudo resolver hojas enlazadas por Jinja. Las imágenes con `src=""` de POS y tienda son vistas previas dinámicas; no se clasifican como fallos sin comprobar su estado visible. Los avisos de jerarquía tampoco se dan por confirmados.
- Playwright se instaló en un entorno virtual aislado y permitió la captura local, después de que el navegador integrado no estuviera disponible y de que la revisión automática rechazara un comando directo de Chrome. No se usaron datos reales. Las plantillas sintéticas se retiraron; las capturas conservadas son solo de prueba.
- Las capturas comprueban seis superficies y el estado vacío/ejemplo; no equivalen a recorrer todos los módulos administrativos, roles, modales, errores, pagos ni cámara. Tampoco se midió contraste efectivo de cada combinación, interacción táctil física o foco con lector de pantalla. La consulta de seguimiento a Antigravity falló con `NotADirectoryError [WinError 267]`; no se atribuye ninguna observación adicional a ese intento.

## Secuencia recomendada para una mejora posterior

1. Corregir la superposición del POS a 390 px y verificar que filtros, búsqueda y acciones se pueden pulsar sin solapamiento en 390, 768 y 1024 px; conservar el layout reconocido en escritorio.
2. Resolver contrastes y etiquetas del POS y seguimiento; comprobar con lector de pantalla los anuncios del kiosco y errores de cobro. Conservar la paleta con pares cromáticos accesibles.
3. Afinar navegación activa y sistema de componentes compartidos. Tratar kiosco como variante de operación, con decisión explícita sobre su paleta y marca.
4. Completar estados de carga, error, éxito y modales por rol; revalidar con navegador, teclado, zoom 200%, lector de pantalla y pruebas UI focalizadas, sin ejecutar pruebas SQL ni alterar datos.

Fuente de criterios: [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md), Impeccable `audit` y búsquedas locales UI/UX Pro Max. Prioridades basadas en evidencia de código y capturas sintéticas; el impacto real requiere validación con flujos y datos de prueba completos.
