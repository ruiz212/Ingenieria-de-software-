# Seguridad y recuperación de la colaboración

## Límites permanentes

- Respetar comportamiento, datos, arquitectura e instrucciones existentes. Preferir cambios pequeños, reversibles y con pruebas adecuadas cuando estén autorizados.
- Excluir `.env`, `*.db`, `scratch/`, cargas de usuarios, archivos generados y cualquier contenido privado de consultas MCP, informes y diffs compartidos. No revelar secretos, tokens, claves ni datos personales a Antigravity.
- No escribir en bases de datos o servicios externos sin autorización específica. No ejecutar migraciones, despliegues, cambios de infraestructura ni comandos destructivos sin autorización. No usar YOLO ni ampliar permisos automáticamente.
- No eliminar ni sobrescribir trabajo previo del usuario. Revisar Git antes y después de modificar. Si aparece un cambio inesperado, detener la actividad afectada y reportarlo sin borrarlo.
- Una propuesta técnica no concede permiso para implementarla. Cualquier cambio funcional o acción externa requiere aprobación explícita y concreta.

## Validación de cambios autorizados futuros

1. Capturar rama y `git status --short` antes del cambio; revisar instrucciones y límites del módulo.
2. Definir aceptación y prueba segura. Las pruebas SQL de este proyecto pueden escribir en QA; no ejecutarlas sin destino aislado y autorización específica. No inferir que `pytest` completo es de solo lectura.
3. Hacer cambio mínimo en archivos acordados, con un integrador. Comparar `git diff --name-status` y diff final con el alcance autorizado.
4. Ejecutar solo validaciones permitidas; registrar qué se probó, resultado, qué no se verificó y cómo revertir mediante el diff propio. No hacer `reset`, `clean` ni borrados sobre trabajo ajeno.

## Riesgos observados y límites de esta inspección

`README.md` advierte que `database/esquema.sql` reconstruye tablas. Los scripts de migración y semillas no se ejecutaron. `docs/` contiene auditorías fechadas con hallazgos y reparaciones; su vigencia requiere comprobación antes de actuar. Docker y el workflow usan versiones de Python distintas. La existencia de un workflow de Azure no demuestra un despliegue operativo ni permisos reales. La consulta MCP inicial no devolvió respuesta; no se puede certificar revisión independiente.
