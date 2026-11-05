# Coordinación de agentes — Brajher's Cake

Estas reglas aplican a Codex y a cualquier agente que trabaje en este repositorio. Leer también `docs/agents/ARCHITECTURE.md`, `COLLABORATION.md`, `TASK_DISTRIBUTION.md`, `SAFETY.md` y `BACKLOG.md`. Las instrucciones del usuario y las reglas previas más restrictivas prevalecen.

## Sistema existente

Aplicación Flask con factory en `app/__init__.py`, seis blueprints (`auth`, `hub`, `pos`, `monitor`, `admin`, `kiosco`), vistas Jinja y recursos en `templates/` y `static/`. `app/db.py` usa `pyodbc` para SQL Server y combina consultas directas con procedimientos almacenados. `database/` contiene scripts de ocho esquemas de dominio. Hay pruebas `pytest` y pruebas de navegador en `tests/browser/`. `Dockerfile` y `.github/workflows/main_brajherscake.yml` describen dos rutas de entrega; su ejecución real no fue comprobada. Fuente y límites: `docs/agents/ARCHITECTURE.md`.

## Responsabilidades iniciales

- **Codex:** coordinación y planificación; implementación o refactorización solo cuando se autorice; pruebas, depuración, validación e integración tras revisión.
- **Antigravity:** segunda opinión de arquitectura, revisión crítica de riesgos, alternativas y evaluación de impacto de propuestas.
- **Ambos:** análisis de problemas, revisión cruzada, dependencias, calidad y seguridad. La asignación es flexible y depende de evidencia y alcance.

## Autorización y protección

- Para cualquier cambio funcional o acción externa, solicitar aprobación explícita y acotada. Una recomendación no autoriza su implementación.
- Preservar comportamiento, datos, arquitectura y trabajo previo. Preferir cambios mínimos, reversibles y comprobados con pruebas pertinentes.
- No leer ni compartir secretos, tokens, claves, datos personales o archivos privados con el otro agente. Solo enviar resúmenes técnicos sanitizados por MCP.
- No escribir en bases de datos ni servicios externos sin autorización específica. No ejecutar migraciones, despliegues ni cambios de infraestructura sin autorización.
- No usar YOLO ni ampliar permisos automáticamente. No eliminar trabajo del usuario. Revisar `git status` antes y después de toda modificación autorizada; detenerse y reportar cambios inesperados.
- Un responsable integra cada cambio; no asignar edición concurrente de los mismos archivos.

## Flujo

Registrar futuras tareas con la plantilla de `docs/agents/BACKLOG.md`; evaluar alcance, dependencias, riesgo y aceptación según `TASK_DISTRIBUTION.md`. La consulta MCP es textual: no proporciona edición remota, memoria compartida ni ejecución paralela. Resolver discrepancias con archivos, pruebas y criterios de aceptación; pedir decisión al usuario si cambia el comportamiento de negocio.
