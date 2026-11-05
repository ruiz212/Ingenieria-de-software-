# Protocolo Codex ↔ Antigravity

Codex coordina. `safe-antigravity.ask_antigravity` permite consulta textual a Antigravity; `safe-codex.ask_codex` permite el sentido inverso. El puente existente no se reconfigura. No garantiza sesión ni memoria compartida, edición remota, ejecución simultánea o acceso a los mismos archivos.

## Consulta

1. Codex inspecciona evidencia pertinente y formula una pregunta acotada. Incluye objetivo, rutas públicas de archivos necesarias, hechos comprobados, incógnitas, criterios de aceptación y límite de respuesta. Envía solo un resumen sanitizado de hasta 4.000 caracteres; nunca contenidos privados, secretos, credenciales ni datos personales.
2. Pide una evaluación independiente, alternativas, dependencias y riesgos, y que marque hechos e inferencias. Prohíbe llamadas recursivas a `ask_codex` y cadenas de delegación.
3. Codex contrasta cada afirmación con el repositorio y pruebas seguras. Registra desacuerdos y evidencia, sin convertir propuestas en órdenes de implementación.
4. Si MCP falla o demora demasiado, registra la limitación y continúa con lo verificable. Evita reintentos indefinidos. En la configuración inicial del 31-10-2026 se hizo **una** consulta y terminó por espera excesiva sin respuesta; no hay hallazgos atribuibles a Antigravity.

Máximo dos consultas a Antigravity durante la configuración inicial; se usó una. En tareas futuras, consultar cuando una segunda opinión pueda cambiar alcance, diseño o riesgo. Evitar duplicar análisis de rutina.

## Decisiones y revisión

Codex conserva el registro de tareas y designa un único integrador. Antigravity puede revisar una propuesta o diff descrito de forma sanitizada. El responsable valida contra código y pruebas antes de aceptar una observación. Para desacuerdos funcionales, presentar alternativas y pedir decisión del usuario; para desacuerdos técnicos, usar evidencia y criterios de aceptación. El MCP de texto no equivale a asignar edición autónoma de archivos ni trabajo paralelo real.
