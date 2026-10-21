# CSS y movimiento

La aplicación conserva Flask/Jinja, CSS nativo y JavaScript. Las fuentes editables y los resultados generados están separados. Las plantillas resuelven cada paquete mediante `css_url()`; no contienen bloques `<style>` ni atributos de presentación `style`.

```text
static/css/
  base/          colores, reset, accesibilidad y tokens de movimiento
  layout/        cabecera, navegación y estructura administrativa
  components/    botones, formularios, tablas, modales, avisos y widgets de venta
  themes/        acabado de marca de acceso, administración, POS y tienda
  pages/
    admin/       gestión, contabilidad, personal, catálogo y DGI
    auth/        acceso, registro, bienvenida y segundo factor
    customer/    tienda y seguimiento
    kiosk/       asistencia del kiosco
    sales/       POS, visuales de producto y monitor
  print/         facturas, comprobantes, estados, nóminas y reportes
  utilities/     ayudas pequeñas compartidas
  legacy/        CSS histórico sin referencias en los paquetes activos
  sources.json   paquetes y orden explícito de sus fuentes
  dist/          resultados generados y manifiesto; no editar a mano

app/assets.py             resolución de URLs y caché del manifiesto
scripts/build_css.py      constructor y comprobación reproducible
tests/test_css_assets.py  contratos de construcción y referencias de plantilla
```

## Editar y compilar

1. Modificar la fuente correspondiente. Las reglas reutilizadas pertenecen a `components/`; los ajustes exclusivos de una pantalla pertenecen a `pages/`. Los documentos imprimibles tienen fuentes propias en `print/`.
2. Si se crea una hoja, registrar su paquete y sus fuentes en `sources.json`.
3. Ejecutar `python scripts/build_css.py` desde la raíz del proyecto.
4. Incluir el paquete con `<link rel="stylesheet" href="{{ css_url('pages/admin/rrhh') }}">`. En una plantilla administrativa heredada, usar el bloque `page_styles` para ajustes de esa pantalla; `extra_head` sigue disponible para otros recursos.
5. Ejecutar `python scripts/build_css.py --check` para detectar resultados desactualizados sin modificarlos.

El constructor comprueba todas las fuentes antes de escribir. Una fuente ausente, repetida o situada fuera del directorio CSS produce un error. Cada paquete recibe una versión derivada de su contenido; `css_url()` recarga el manifiesto cuando cambia. Entregar `dist/` junto con las fuentes: la aplicación sirve estos archivos y no compila CSS durante las solicitudes.

## Clases y cascada

Las pantallas usan un scope `page-*` en el cuerpo y clases prefijadas por módulo. Por ejemplo, `.page-catalogo-cuentas .account-code` define una pieza de esa pantalla, mientras `.btn` es un componente compartido. Los IDs y las clases utilizadas por JavaScript se conservan como contrato de interacción. Un nombre semántico puede ser un punto de conexión de JavaScript y no necesita una regla CSS propia.

Los estilos calculados por estado se expresan mediante clases: `account-level-1`, `result-profit`, `result-loss`, `asistencia-record-absent`, `quote-status-pending`. El CSS de los fragmentos de carrito, cotizaciones y ticket generados por `static/js/pos.js` vive en `components/_sales-widgets.css`, compartido por la tienda y el POS.

Orden general: estructura compartida, estilos específicos, accesibilidad/tema, ajustes de página y movimiento al final. `sources.json` es la autoridad del orden dentro de cada paquete. Evitar nuevas copias dentro del HTML, selectores por posición del DOM y `transition: all`. Los valores realmente calculados en ejecución, como el ancho de un indicador, la visibilidad controlada por JavaScript o la duración de un aviso, permanecen en su controlador; no son una segunda hoja de estilos.

## Movimiento

`base/_motion-tokens.css` define las duraciones por propósito: 90ms para presión, 160ms para respuesta, 220ms para cambios breves, 260ms para entradas, 280ms para apertura de panel y 380ms para movimientos amplios. Las salidas usan 180ms. Los nombres anteriores `--transition-fast`, `--transition-smooth` y `--transition-slow` se conservan como alias.

`components/_motion.css` reúne entradas de pantalla, controles, modales y paneles. La pantalla presenta una o dos entradas principales; las filas y cifras no se animan una por una. El carrito y el menú se desplazan con `transform`, manteniendo `right` fijo. Las entradas terminan sin un `transform` permanente ni `will-change` persistente. La preferencia `prefers-reduced-motion: reduce` y la impresión eliminan las transiciones y animaciones y conservan los estados finales legibles. Los indicadores de carga pueden moverse mientras hay una operación activa; las cifras en reposo no parpadean continuamente.

## Validación

Los scripts de `tests/browser/` usan Edge/Playwright instalado y un servidor QA local. `PLAYWRIGHT_MODULES` apunta al directorio de módulos si no está en Node. `WEB_UI_BASE_URL` indica la URL QA y `WEB_UI_ACCESS_FILE` un JSON local ignorado con una cuenta de prueba existente. Nunca usar la conexión real para pruebas con escrituras.

- `web_ui.mjs`: siete pantallas operativas, navegación móvil, foco, confirmaciones, acceso y descargas.
- `store_ui.mjs`: catálogo entre 320 y 1440px, búsqueda, filtros y carrito, sin emitir pedidos.
- `motion_ui.mjs`: movimiento normal y reducido, interrupción rápida del menú, confirmación, carrito y recuperación del foco.
- `styles_pages.mjs`: gestión y contabilidad ampliadas, fuentes CSS cargadas y estados de impresión.

La revisión independiente encontró tres hojas contables que no coincidían con las clases extraídas; se reconstruyeron desde la copia exacta de partida, conservando sus estados calculados. Se auditaron las 392 clases extraídas y se corrigieron también dos reglas faltantes de registro y segundo factor. La evidencia local de esta revisión está en `scratch/css_motion/`, sin datos de acceso en los documentos versionados.
