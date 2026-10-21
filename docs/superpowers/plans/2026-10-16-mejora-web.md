# Mejora de la experiencia web

> **For agentic workers:** Implementar en esta sesión con verificación de comportamiento y una revisión independiente final.

**Goal:** Mejorar el acceso, la orientación y el uso móvil de la aplicación existente.

**Architecture:** Conservar Flask/Jinja, los permisos por rol y la marca café/ámbar. Mejorar los componentes compartidos para beneficiar todas las páginas administrativas y refinar el acceso y el resumen diario sin cambiar cálculos ni registros.

**Tech Stack:** Flask, Jinja, CSS con variables y JavaScript nativo. Playwright/Edge para verificación.

**Spec:** Petición del usuario «utiliza todas las skills y quiero que mejores la web» y autorización «avanza con tu criterio». Decisiones de implementación del agente: conservar identidad, priorizar la operación y ejecutar aquí.

## Restricciones

- No modificar datos comerciales, perfiles fiscales, permisos ni fórmulas.
- No instalar un framework ni dependencias nuevas en la aplicación.
- Mantener rutas, CSRF, sesiones y formularios existentes.
- Verificar en SQL Server QA independiente; ninguna escritura de prueba en Azure.
- Conservar trabajo ajeno. Entregar cambios locales revisables.

## Focos de revisión

- Menú móvil cerrado: enlaces fuera del orden de tabulación; abierto: secciones y salida accesibles.
- Búsqueda de opciones: acentos, cero resultados, borrado y opción activa.
- Teclado: Escape, foco de regreso y confirmaciones sin activación accidental.
- Acceso: errores persistentes visibles, contraseña accesible y formulario usable con poco alto.
- Pantallas pequeñas y tema oscuro: títulos largos, cifras, tablas y contraste.

## Tareas

- [x] Capturar el estado inicial y establecer una prueba de comportamiento que falle con el menú actual.
- [x] Unificar navegación lateral, buscador de módulos, cabecera, foco y confirmación; refinar superficies y controles compartidos.
- [x] Refinar acceso, entrada de clientes y resumen diario con acciones reales y estados vacíos útiles.
- [x] Compilar CSS, verificar escritorio/móvil/oscuro/teclado y regresión funcional; revisar y documentar resultados.

## Skills aplicadas

Superpowers: planificación, verificación y revisión. Grill Me: aclaración inicial y exploración de hechos; el usuario delegó los detalles. UI/UX Pro Max: búsqueda de recomendaciones por producto y accesibilidad (se descartó un resultado inicial de LMS por no corresponder). Impeccable: refinamiento sobre la implementación existente y comprobación visual. Design Engineer: tokens, componentes compartidos y estados accesibles, adaptados al stack existente. Taste: criterio de tipografía/composición para el acceso público, sin trasladar reglas de marketing a las pantallas operativas.

## Resultado

Implementado y verificado. Ver `docs/MEJORA_WEB_2026-10-16.md`. Suite: 135 aprobadas; navegador: siete pantallas a tres anchos y dos accesos públicos, sin errores JavaScript. Revisión independiente final sin hallazgos pendientes.
