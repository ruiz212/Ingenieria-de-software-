# Brajher's Cake: mostrador cálido

El usuario pide expresamente `frontend-design`, referencias del sector y una web que destaque, con menos formas cuadradas. Mantiene su autorización de avanzar con criterio.

## Referencias observadas

- GAIL's: https://gails.com/ — protagonismo del pan, categorías y fotografías del producto.
- Loyverse Café: https://loyverse.com/cafe-pos — categorías, pedidos y controles de operación reconocibles.
- Lightspeed Bakery & Café: https://www.lightspeedhq.com/pos/retail/bakery-and-cafe-pos-system/ — continuidad entre ventas, inventario y reportes.

Son referencias de composición y organización; no se copian textos, logos ni imágenes de esas marcas.

## Decisiones de diseño

**Paleta de marca conservada:** café profundo #4E2A1E, cacao #6B3A2A, miel #D4952B, crema #F5F0EA, superficie #FEFCF9 y texto #3B2218. Verde reservado para estados positivos.

**Tipografía:** Playfair Display en marca y títulos de bienvenida; Inter en controles, tablas y cifras del sistema. Conservar las familias propias de la tienda para evitar cambios de métricas tipográficas innecesarios.

**Formas:** controles de 14–16px, paneles de 24px, marco de acceso de 32px y botones primarios redondeados. El logo BC adopta un sello circular. Las tablas conservan alineación y lectura clara; no se convierten en cápsulas.

**Composición:** el acceso deja de ser dos rectángulos pegados a los bordes: un marco crema contiene una fotografía redondeada y el formulario. En móvil se conserva una única superficie respirable con marca completa.

```text
Escritorio                       Móvil
╭──────────────────────────╮      ╭────────────────╮
│ ╭foto + marca╮  acceso    │      │ sello + marca  │
│ │ bienvenida│  campos    │      │ bienvenida     │
│ ╰───────────╯  acción    │      │ campos / acción│
╰──────────────────────────╯      ╰────────────────╯
```

**Criterio:** calidez basada en los productos y colores del negocio; sombras suaves sólo para separar superficies. No introducir adornos que dificulten trabajar, falsas cifras ni servicios inexistentes.

## Implementación y verificación

- [x] Añadir una capa de diseño compartida, acotada a las páginas existentes, para acceso, administración, tienda y POS.
- [x] Integrar sus enlaces después de las hojas de estilo específicas; conservar rutas, IDs, permisos y formularios.
- [x] Revisar escritorio, móvil y tema oscuro; comprobar también el catálogo de cliente y su carrito sin emitir pedidos.
- [x] Ejecutar las pruebas funcionales y una revisión independiente, después actualizar el servidor local.

## Evidencia y correcciones

La nueva capa `static/css/bakery.css` se carga después de los estilos de cada página. Se limita a pantalla para conservar los estilos de impresión existentes. Se inspeccionaron capturas reales del acceso, panel, DGI oscuro, tienda y carrito.

La prueba del catálogo encontró dos defectos anteriores al rediseño:

- La cabecera de 390px extendía búsqueda y pedido hasta 534px. Se reorganiza en filas a partir de 600px, con límites de anchura para la cuenta.
- Buscar o filtrar añadía `.hidden`, pero la regla posterior `display:flex!important` de las tarjetas las mantenía visibles. Se confirmó también con la nueva capa desactivada. `.store-product-card.hidden` resuelve la prioridad en las dos fuentes existentes de la tienda.

`tests/browser/store_ui.mjs` conserva comprobaciones del catálogo a 1440, 768, 390 y 320px, límites geométricos de búsqueda/pedido, búsqueda sin resultados, categorías y agregado/apertura/cierre del carrito. Intercepta cualquier escritura accidental y no envía pedidos. La revisión independiente detectó dos selectores sin destino real; se corrigieron y la segunda revisión no encontró problemas bloqueantes.

Resultado final: 135 pruebas Python/SQL aprobadas; suites de navegador operativas y de tienda sin errores. Servidor local de 5000 actualizado y verificado mediante GET del acceso y bienvenida y comparación exacta de la hoja CSS servida con el archivo local. Se cerró el servidor temporal QA de 5071 después de verificar.
