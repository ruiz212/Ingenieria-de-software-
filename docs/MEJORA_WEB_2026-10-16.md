# Mejora de la experiencia web · 16 de octubre de 2026

La mejora conserva Flask/Jinja y la identidad café y ámbar de la panadería. No cambia permisos, cálculos contables ni datos comerciales. Las decisiones de presentación se tomaron con la autorización del usuario «avanza con tu criterio».

## Cambios visibles

- Navegación administrativa con nombres visibles y búsqueda de secciones. Respeta las opciones disponibles para cada rol, permite buscar sin acentos, indica cuando no encuentra coincidencias y permite limpiar la búsqueda.
- Un único menú móvil vertical sustituye la combinación defectuosa de una barra horizontal y un panel lateral. Mantiene disponible Salir, admite interacción táctil, controla el foco y cierra con Escape o al pulsar fuera.
- Resumen del día con accesos a las tareas existentes, cifras legibles y estados vacíos que indican el siguiente paso.
- Acceso y bienvenida de clientes más claros y adaptables al alto disponible. Los errores de autenticación permanecen visibles y el control de contraseña anuncia su estado.
- Superficies, botones, tablas y cabecera más consistentes; contraste corregido para acciones principales, incluido hover, y controles de tema con nombre accesible.
- Búsquedas de inventario/catálogo con nombres accesibles, acciones de inventario sin recortes en móvil y selección de imágenes operable por teclado.

## Correcciones de interacción

La confirmación compartida usa un diálogo nativo: el foco comienza en Cancelar, Escape cancela y el foco regresa al control anterior. Los formularios cuya lógica cancela el envío nativo no quedan bloqueados por el manejador global. Las descargas DGI declaran `data-download`: recibir un archivo, incluso mediante redirección, permite repetir la descarga.

Al revisar el punto de venta se reprodujo un error anterior: con turno cerrado, JavaScript intentaba asociar un evento al catálogo que la plantilla no mostraba. Se hizo opcional esa asociación, conservando el flujo de apertura de turno.

## Verificación

- Suite Python/SQL Server: **135 pruebas aprobadas**, una advertencia de obsolescencia de Flask-Login. Ejecución exclusivamente sobre la base local `PanaderiaQA_Prevalidacion_20261015`.
- Prueba de navegador `tests/browser/web_ui.mjs`: acceso real con cuenta QA existente, menú, búsqueda, foco, confirmación, envíos cancelados, descargas repetidas y error de autenticación. Las descargas de esta prueba se interceptan en el navegador y no producen operaciones fiscales.
- Siete pantallas operativas: resumen, inventario, contabilidad, DGI, catálogo, punto de venta y monitor a 1440, 768 y 390 px. Acceso y bienvenida de clientes a 1440 y 390 px. Tema oscuro y acceso con sólo 400 px de alto.
- Edge con eventos táctiles sintetizados y teclado; esta evidencia no corresponde a un dispositivo físico.
- Plantillas Jinja compiladas, sintaxis JavaScript comprobada y CSS recompilado con `python scripts/build_css.py`.
- Revisión independiente: detectó el bloqueo de una descarga DGI; se añadió una prueba que falló antes de corregirlo y después permitió dos descargas sucesivas.

El detector de Impeccable no interpreta las rutas Jinja de las hojas de estilo y produjo avisos estáticos de jerarquía tipográfica incorrectos. La inspección de la página renderizada no reprodujo esos avisos; señaló una curva de animación heredada como recomendación estética. Se preservó el comportamiento operativo con movimiento reducido, sin añadir animaciones decorativas. La imagen de acceso y las fuentes conservan sus proveedores externos existentes.

## Skills utilizadas

Superpowers aportó planificación, depuración, pruebas y revisión independiente. Grill Me permitió aclarar la intención; el usuario delegó las decisiones. UI/UX Pro Max aportó la búsqueda específica para panadería y navegación accesible; se descartó una búsqueda inicial que correspondía a un LMS. Impeccable se aplicó como refinamiento de una aplicación operativa. Design Engineer aportó componentes compartidos, tokens y estados accesibles adaptados a Flask. Taste aportó criterios de composición y tipografía al acceso, sin imponer requisitos de una página publicitaria al sistema de trabajo.

## Repetir la verificación de navegador

Requiere Node y Playwright con Edge, un servidor QA local y `WEB_UI_ACCESS_FILE` apuntando a un JSON local no versionado con `usuario`, `clave` y `revision` de prueba. `WEB_UI_BASE_URL` identifica el servidor local y `PLAYWRIGHT_MODULES` puede señalar el directorio que contiene Playwright. Ejecutar `node tests/browser/web_ui.mjs`. Las capturas y el resultado se guardan en `scratch/web_ui/`.


## Segunda ronda solicitada: agentes de diseño

Se lanzaron cuatro agentes con tareas de archivos independientes. Taste refinó el acceso y unificó la marca en móvil sin eliminar Panadería Amada. UI/UX Pro Max compactó la cabecera móvil de tres filas a una franja de 76 px, mantuvo cuenta y Salir en el menú y añadió una pista de desplazamiento para las secciones largas. Impeccable agrupó los indicadores, convirtió el detalle en tablas semánticas y organizó los turnos como un panel lateral en escritorio. Design Engineer revisó la integración y los últimos ajustes, sin hallazgos pendientes.

La nueva prueba integrada también comprueba la cabecera compacta, búsqueda de Producción sin tilde y el ciclo Tab/Shift+Tab dentro del menú. El panel se probó con datos vacíos y poblados, nombres largos e importes millonarios, en claro/oscuro y sin JavaScript. Se conservó el cálculo existente que devuelve 100% si no hay encargos; esta ronda modifica presentación, no reglas de negocio. La suite completa volvió a pasar: 135 pruebas.

## Tercera ronda: frontend-design y formas más suaves

El usuario pidió expresamente `frontend-design`, referencias del sector y menos formas cuadradas. Se observaron GAIL's (https://gails.com/) y Loyverse Café (https://loyverse.com/cafe-pos): protagonismo del pan y claridad de las tareas. La propuesta conserva los colores café y miel del negocio, con un marco fotográfico redondeado en el acceso, sello circular, radios diferenciados entre superficies y controles y acciones en forma de cápsula. Se aplica al acceso, bienvenida, administración, DGI, POS y tienda. Los recursos fotográficos y familias tipográficas existentes se conservan.

La revisión en Edge encontró y corrigió dos defectos heredados de la tienda: el pedido quedaba recortado en móvil y los filtros no ocultaban tarjetas porque su `display:flex!important` prevalecía sobre `.hidden`. Los selectores de la nueva capa se verificaron contra los elementos reales. Una segunda revisión independiente no encontró problemas bloqueantes.

Verificación de esta ronda: 135 pruebas Python/SQL aprobadas en 33,86s, con una advertencia existente de obsolescencia de Flask-Login; suite de navegación de siete secciones sin errores; nueva prueba `tests/browser/store_ui.mjs` con catálogo a 1440/768/390/320px, búsqueda, categoría y carrito. Los datos de prueba pertenecen a la copia SQL local QA; no se emitió ningún pedido. Capturas y resultados: `scratch/bakery_soft/final/`. Para repetir la prueba de tienda, usar las mismas variables de Playwright y servidor QA y ejecutar `node tests/browser/store_ui.mjs`; no requiere credenciales porque utiliza el invitado QA existente.
