# Reparación UX/UI del informe de 44 hallazgos

> Implementación en la sesión actual. Cada grupo se verifica en archivos fuente; `static/css/dist` se genera una sola vez al integrar.

**Objetivo:** Corregir las barreras de uso y accesibilidad comprobadas en el informe del 1 de noviembre de 2026, preservando datos, permisos, cálculos y la identidad visual existente.

**Arquitectura:** Flask/Jinja, CSS fuente por componente/página y JavaScript existente. Cambios de comportamiento de interfaz se cubren con pruebas aisladas; ninguna prueba realiza operaciones de negocio ni escrituras a SQL real.

**Criterios globales:** Acciones esenciales alcanzables en 320, 390, 768, 1024 y 1366 px; diálogos operables por teclado; campos con nombre accesible; textos legibles en claro y oscuro; estados y períodos no engañosos; compilar `static/css/dist` con `scripts/build_css.py`.

## Grupos de trabajo

- [ ] **Tablas y accesibilidad administrativa (#05, #06, #09, #11, #12, #13, #34, #39).** Catálogo, clientes, usuarios, auditoría y estadística. Probar diálogo de producto, etiquetas, gráficos y acciones de tabla.
- [ ] **Fiscal y contabilidad (#10, #11, #25–27, #35–38, #43).** Separar tareas sin cambiar cálculos ni estado persistente; corregir contraste, períodos, vacíos y grid. Probar render y semántica con datos sintéticos.
- [ ] **Operación y personas (#21–24, #28, #29, #31, #32).** Distinguir caja/turno, ordenar RRHH, corregir conteos y lectura de inventario, producción, asistencia y monitor. Probar con datos sintéticos.
- [ ] **Público y sistema compartido (#01–04, #07, #08, #14–20, #30, #33, #40–44).** Revisión de entradas, tienda, navegación, tokens y adaptación. Las decisiones comerciales se basan en respuesta del dueño; sin respuesta, preservar prioridad y datos actuales.
- [ ] **Integración y verificación.** Revisar diffs, resolver conflictos, compilar CSS, ejecutar pruebas seguras, inspeccionar navegador a tamaños representativos y documentar límites pendientes.

## Límites de este pase

No se cambian categorías, registros reales, tasas, salarios, permisos, migraciones, pedidos ni operaciones de caja. Recomendaciones que dependan de esos datos o de una decisión comercial se documentan con evidencia y no se simulan como resueltas.

## Avance verificado el 2 de noviembre

- Correcciones en vistas administrativas, contabilidad, RRHH, tienda y monitor integradas en fuentes y CSS compilado. Una revisión independiente detectó dos problemas adicionales de foco y fecha; se corrigieron antes de cerrar este pase.
- `python -m pytest` sobre 14 archivos de pruebas aisladas: 167 aprobadas. No se ejecutó la suite SQL ni operaciones de negocio.
- Pruebas de navegador con datos sintéticos: diálogo de producto, bolsa y diálogo de pedido; acciones de Catálogo visibles y tienda sin desbordamiento de página a 320, 390, 768, 1024 y 1366 px.
- `python scripts/build_css.py --check`, `node --check` en los JavaScript modificados y `git diff --check`: correctos.
- Siguen pendientes la validación manual de tema oscuro, zoom, impresión y flujo de venta/caja en un entorno de prueba autorizado, además de decisiones de negocio indicadas en el informe. Las casillas de grupos se conservan abiertas hasta comprobar cada recomendación contra su criterio de aceptación.
