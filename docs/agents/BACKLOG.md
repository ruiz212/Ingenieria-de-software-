# Plantilla de tareas futuras

## TASK-2026-002 — Asistente WhatsApp

- Solicitud: implementación autorizada el 04-11-2026 tras revisión de viabilidad.
- Objetivo: atención por catálogo, cotizaciones del canal y seguimiento, con control humano.
- Alcance: `app/whatsapp`, migración `06_whatsapp_bot.sql`, hooks POS/KDS, panel y documentación.
- Dependencias: SQL Server migrado, Neonize 0.10.0, clave Gemini, sesión de WhatsApp y almacenamiento compartido.
- Prioridad y complejidad: alta; cruza canal externo, permisos SQL y transacciones comerciales.
- Criterios: identidad fuera del modelo, confirmaciones explícitas, deduplicación, reintentos,
  pausa humana, CSRF y pruebas sin tocar la base operativa.
- Responsable e integrador: Codex; programación sin delegación a solicitud del usuario.
- Participación de Antigravity: consulta arquitectónica en la revisión previa.
- Aprobación recibida: código y pruebas locales; no se activó una cuenta ni se aplicaron migraciones.
- Estado: implementado localmente; pendiente de verificación SQL Server QA y vinculación controlada.
- Evidencia: plan `docs/superpowers/plans/2026-11-04-whatsapp.md`, manual `docs/WHATSAPP.md`.

No hay tareas nuevas registradas por esta configuración. Copiar la plantilla siguiente solo cuando exista una solicitud concreta; no tratar auditorías históricas como órdenes de trabajo.

```markdown
## TASK-AAAA-NNN — Título

- Solicitud y fecha:
- Objetivo:
- Alcance y exclusiones:
- Componentes y archivos potencialmente afectados:
- Dependencias y orden:
- Prioridad y complejidad: baja | media | alta
- Riesgo y datos/servicios afectados:
- Criterios de aceptación:
- Validación segura prevista:
- Responsable:
- Integrador único:
- Participación de Antigravity: ninguna | consulta | revisión
- Aprobación explícita requerida/recibida:
- Estado: propuesta | en análisis | pendiente de aprobación | autorizada | en curso | en revisión | cerrada
- Evidencia, decisiones y limitaciones:
```

Antes de pasar a `autorizada`, precisar cualquier cambio funcional o acción externa y obtener aprobación explícita del usuario. Mantener identificadores únicos y actualizar estado solo con evidencia.

## TASK-2026-001 — Auditoría integral del diseño existente

- Solicitud y fecha: revisión conjunta con Antigravity del diseño de toda la aplicación, 31-10-2026.
- Objetivo: identificar mejoras de UX, accesibilidad y consistencia sin perder la identidad visual ni la paleta actual.
- Alcance y exclusiones: análisis de plantillas, CSS y flujos representados; no incluye cambios funcionales, base de datos ni despliegue.
- Componentes y archivos potencialmente afectados: `templates/`, `static/css/`, JavaScript de avisos y formularios; ver `DESIGN_AUDIT_2026-10-31.md`.
- Dependencias y orden: seis superficies principales ya se capturaron con datos sintéticos; completar estados y módulos restantes antes de cambios amplios. Priorizar el bloqueo táctil del POS móvil.
- Prioridad y complejidad: alta; cruza seis superficies y componentes compartidos.
- Riesgo y datos/servicios afectados: experiencia de cobro, pedidos, administración y asistencia; no se trataron datos reales.
- Criterios de aceptación: conservar colores y carácter visual; contrastes AA en texto normal, etiquetas de formulario programáticas, avisos anunciados y estados distinguibles sin depender solo del color; comprobar escritorio y móvil.
- Validación segura prevista: capturas realizadas a 390/1440 px y prueba focalizada de clic a 390/768/1024 px; pendiente teclado, zoom, estados y módulos restantes, sin SQL.
- Responsable: Codex.
- Integrador único: Codex, solo si se autoriza una implementación posterior.
- Participación de Antigravity: consulta textual de riesgos y criterios; sin acceso al repositorio ni a pantallas.
- Aprobación explícita requerida/recibida: análisis autorizado; cambios funcionales pendientes de alcance y aprobación específica según `AGENTS.md`.
- Estado: en análisis.
- Evidencia, decisiones y limitaciones: `DESIGN_AUDIT_2026-10-31.md` y capturas sintéticas. La primera consulta extensa agotó 45 s; la segunda obtuvo respuesta en 19 s. El intento de seguimiento falló con `WinError 267`. El navegador integrado no estuvo disponible; se instaló Playwright en entorno aislado para capturar con Chrome local. Se comprobó superposición que bloquea filtros/búsqueda del POS a 390 px.
