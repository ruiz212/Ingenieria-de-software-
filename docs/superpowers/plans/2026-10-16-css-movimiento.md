# CSS y movimiento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para ejecutar las tareas en esta sesión y una revisión independiente al terminar.

**Goal:** Organizar todas las fuentes CSS y unificar animaciones accesibles en la aplicación existente.

**Architecture:** Paquetes reproducibles desde `static/css/sources.json`, fuentes separadas por responsabilidad y manifiesto con hashes. Plantillas con `css_url()` y clases estáticas, movimiento compartido al final de la cascada.

**Tech Stack:** Flask/Jinja, Python estándar, CSS y JavaScript nativos, Edge/Playwright instalado.

**Spec:** `docs/superpowers/specs/2026-10-16-css-movimiento-design.md`.

## Global Constraints

Conservar IDs, rutas, roles, CSRF y cálculos. Sin dependencias nuevas. Pruebas de datos sólo en SQL local PanaderiaQA_. Preservar todos los cambios anteriores. Sin commits ni publicación.

## Review Focus

- Estilos de impresión cargan sin heredar movimientos ni alterar comprobantes.
- Una plantilla heredada conserva sus propios estilos después del tema compartido.
- Menús, diálogos y carrito siguen abriendo/cerrando con teclado y movimiento reducido.
- CSS generado es reproducible; una fuente ausente detiene la compilación antes de cambiar resultados.
- Clases condicionales y estilos de contenido generado por JavaScript conservan estados y prioridad.

## Tarea 1 — Constructor y manifiesto

Archivos: `scripts/build_css.py`, `static/css/sources.json`, `app/assets.py`, `app/__init__.py`, `tests/test_css_assets.py`.

- [x] Probar error por fuente ausente, construcción determinista y cambio de versión con contenido; ver fallar antes de implementar.
- [x] Implementar `build_css(base_dir=None)` y `init_assets(app)`; validar rutas dentro de static/css, conservar orden explícito y generar manifiesto de paquetes.
- [x] Verificar prueba y URLs Jinja en contexto Flask sin SQL.

## Tarea 2 — Fuentes y clases

Archivos: fuentes en `static/css/{base,layout,components,themes,pages,print,utilities}`, plantillas existentes, `docs/CSS.md`.

- [x] Extraer bloques estáticos a su hoja de página/impresión, conservar orden y unificar las dos fuentes de tienda/registro.
- [x] Migrar atributos estáticos a clases descriptivas y estados condicionales; conservar estilos calculados realmente necesarios.
- [x] Separar el tema de acceso, administración, POS y tienda; retirar entradas antiguas después de actualizar referencias.
- [x] Compilar y comprobar referencias locales, plantillas y resultados del navegador contra capturas de partida.

## Tarea 3 — Sistema de movimiento

Archivos: `static/css/base/_motion-tokens.css`, `static/css/components/_motion.css`, hojas de página/componentes y script de navegación si hace falta.

- [x] Añadir prueba de navegador que falle ante ausencia de movimiento normal y que compruebe estados finales con movimiento reducido.
- [x] Unificar tiempos/curvas, eliminar `transition:all`, centralizar keyframes compartidos y detener adornos infinitos.
- [x] Mejorar respuestas de controles, menú, diálogos, carrito y entrada de pantalla sin retrasar tareas ni animar cada fila.
- [x] Verificar interrupciones rápidas, teclado y movimiento reducido en las pantallas principales.

## Tarea 4 — Integración

- [x] Ejecutar suites de navegador, pruebas Python/SQL y compilación reproducible; inspeccionar escritorio, móvil y oscuro.
- [x] Revisión independiente acotada y corrección de hallazgos reales.
- [x] Documentar estructura, edición/compilación y evidencia. Actualizar el servidor local y verificar assets servidos.

## Registro de ejecución

- Decisión: ejecución continua en este checkout, con copia de partida; el usuario delegó los detalles y pide mejorar la versión ya abierta.
- Decisión: CSS nativo con constructor Python, sin librerías de animación adicionales; evita dependencias para microinteracciones de una aplicación de trabajo.
- Decisión: se conserva la escala semántica de 90/160/220/260/280/380ms y se añaden salidas de 180ms; los alias de transición anteriores siguen funcionando.
- Revisión: se reconstruyeron tres hojas contables desde la copia exacta y dos reglas ausentes de acceso; auditoría de 392 clases. Se verificaron 54 reglas de los fragmentos del controlador POS y se actualizó su versión en las dos pantallas.
- Inspección visual: acciones RRHH se envolvieron en dos columnas en móvil para evitar etiquetas recortadas; las tablas utilizan su contenedor de desplazamiento y conservan el ancho completo. Se corrigió el contraste de la cabecera de cuentas y se eliminaron dos landmarks main anidados.
- Resultado: 141 pruebas Python/SQL aprobadas (una advertencia previa de Flask-Login), seis pruebas de assets, cuatro suites de navegador aprobadas, incluyendo 18 páginas ampliadas e impresión. CSS generado reproducible; fuentes y resultados separados. Sin commits ni publicación.
