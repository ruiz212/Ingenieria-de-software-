# Refinamiento de diseño con agentes especializados

**Petición:** lanzar los agentes de diseño instalados y mejorar la web con ellos. El usuario mantiene la autorización previa «avanza con tu criterio».

**Dirección común:** conservar la marca café/ámbar de Brajher's Cake y el nombre Panadería Amada, la tecnología Flask/Jinja, los datos y los flujos comerciales. Mejorar la composición y la consistencia de las superficies existentes; no crear métricas, promesas o funciones ajenas al pedido.

## Asignación sin ediciones concurrentes del mismo archivo

- [x] Taste: acceso y bienvenida; `templates/login.html`, `templates/cliente_bienvenida.html`, `static/css/pages/_login.css`.
- [x] UI/UX Pro Max: orientación y cabecera compacta; `templates/admin_base.html`, `templates/admin/sidebar.html`, `static/css/layout/_sidebar.css`, `static/js/common.js`.
- [x] Impeccable: panel operativo; `templates/admin/dashboard.html`, `static/css/pages/dashboard.css` con estilos acotados.
- [x] Design Engineer: revisión independiente de coherencia, responsive, semántica y contratos de integración.
- [x] Coordinación Superpowers: recompilar, ejecutar pruebas existentes y ampliarlas si aparecen comportamientos nuevos, revisar capturas y servir la versión final.

Grill Me se usa para revisar intención y supuestos; no se repite la entrevista que el usuario pidió delegar. La exploración y las decisiones reversibles se resuelven entre los agentes.

## Verificación

Las pruebas de interacción usan la base local QA existente y el servidor 127.0.0.1:5070. No se prueban escrituras en Azure. Mantener CSRF, nombres de campos y roles, errores persistentes, buscador de módulos, navegación por teclado, confirmación segura y contrato `data-download`. Comprobar al menos 1440, 768 y 390 px, tema oscuro y acceso con poco alto.

## Entrega

Cambios locales sobre el trabajo anterior, sin reset, publicación ni commits de trabajo ajeno. Recompilar el CSS y refrescar el servidor local de la aplicación tras la revisión.

## Resultado verificado

Cuatro agentes: Taste, UI/UX Pro Max, Impeccable y Design Engineer. Implementación y revisión completas. Suite Python/SQL: 135 aprobadas, una advertencia heredada de Flask-Login. Prueba integrada de siete rutas y accesos públicos, teclado, foco, búsqueda sin acentos, descargas y contraste: sin errores JavaScript. Agentes comprobaron además acceso hasta320px, dashboard poblado/vacío con importes largos y navegación sin JavaScript. Capturas y resultados locales en `scratch/diseno_agentes/`, `scratch/taste_*`, `scratch/uiux_*` y `scratch/web_ui/dashboard-v2-*`.
