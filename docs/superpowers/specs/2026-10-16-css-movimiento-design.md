# CSS y movimiento de Brajher's Cake

El usuario pide UI/UX Pro Max, mejores animaciones en toda la web y una distribución clara de CSS, archivos y clases. Conserva la autorización anterior de avanzar con criterio. Se trabaja en el mismo checkout porque contiene la versión que el usuario está usando y cambios previos sin confirmar; se tomó una copia local de los archivos de partida en scratch.

## Resultado esperado

- Una fuente CSS por responsabilidad: base, layout, componentes, temas, páginas (administración, acceso, venta, clientes, kiosco) e impresión. Los archivos generados viven en `static/css/dist/` y nunca se editan a mano.
- El HTML deja de contener bloques de CSS y estilos estáticos repetidos. Las clases de página tienen un prefijo identificable y nombres ligados a su elemento; se conservan IDs y clases que JavaScript utiliza. Los estilos que representan datos calculados se expresan mediante estados o valores dinámicos, sin inventar datos.
- Un constructor Python determinista valida todas las fuentes antes de escribir, genera los paquetes y un manifiesto con versiones por contenido. Una función Jinja resuelve las URLs para evitar versiones manuales desincronizadas.
- Movimiento por propósito: presión de 90ms, respuesta breve de 160ms, cambios breves de 220ms, entrada de 260ms, apertura de panel de 280ms y movimientos amplios de 380ms; salidas de 180ms. Transform y opacidad para desplazamientos; cambios de color para estados. Nada debe quedar oculto si JavaScript no funciona. Sin rebotes constantes en indicadores ni flotación decorativa infinita.
- Movimiento reducido elimina animaciones y transiciones, mantiene los estados finales y todos los controles utilizables. La impresión queda inmóvil.

## Límites

Conservar Flask/Jinja, CSS nativo y JavaScript existente, colores y formas aprobados, rutas, permisos, formularios, datos y cálculos. Sin dependencias nuevas, sin migración a otro framework, sin pedidos ni escrituras fiscales en el servidor real. Sólo la copia local SQL `PanaderiaQA_` para pruebas con datos. No confirmar ni publicar cambios de Git.

## Evidencia

UI/UX Pro Max: búsquedas verificadas `micro interaction easing reduced motion`, dominio UX: movimiento reducido, curvas por propósito y máximo 1–2 entradas clave por pantalla. Verificación mediante pruebas del constructor/manifiesto y navegador con movimiento normal y reducido, menú, confirmación, catálogo/carrito, teclado, tamaños móviles y ausencia de estilos perdidos. La suite funcional SQL se ejecuta al terminar.
