# Distribución de tareas futuras

## Procedimiento

1. Recibir la solicitud y distinguir análisis autorizado de cambios funcionales o acciones externas que requieren aprobación explícita.
2. Identificar objetivo, alcance, módulos y archivos potenciales, prioridad, riesgos, datos afectados y dependencias. Estimar complejidad **baja**, **media** o **alta** según número de límites cruzados, incertidumbre y validación necesaria.
3. Elegir Codex, consulta textual a Antigravity o revisión conjunta. Hacer una sola consulta enfocada si basta para despejar el riesgo; no repetir exploración ya resuelta.
4. Registrar tarea con ID, objetivo, alcance, archivos potenciales, dependencias, criterios de aceptación, riesgo, complejidad, responsable, integrador y estado. Usar `BACKLOG.md` como plantilla; no llenar tareas no solicitadas.
5. Acordar límites de archivos y orden de dependencias antes de cualquier implementación autorizada. No asignar edición concurrente de los mismos archivos. Proponer trabajo paralelo solo si existe infraestructura real que lo permita y tareas independientes; este MCP es solo consulta textual.
6. Validar resultados con evidencia del repositorio y pruebas pertinentes. Resolver desacuerdos técnicos con evidencia; escalar decisiones funcionales al usuario. Un único responsable integra cada cambio tras revisión.

## Matriz inicial

| Situación | Responsable inicial | Participación adicional | Condición |
| --- | --- | --- | --- |
| Lectura y plan acotado | Codex | Antigravity si hay incertidumbre arquitectónica material | Sin cambios funcionales. |
| Implementación/refactorización | Codex | Revisión de Antigravity según riesgo | Aprobación explícita, alcance y criterios definidos. |
| Cambio transversal o sensible | Codex coordina | Antigravity evalúa impacto y alternativas | Separar dependencias; no asumir ejecución paralela. |
| Desacuerdo sobre reglas de negocio | Codex documenta opciones | Antigravity puede criticar | Usuario decide antes de modificar. |

La matriz es flexible: capacidad y evidencia de la tarea prevalecen sobre una especialización fija.
