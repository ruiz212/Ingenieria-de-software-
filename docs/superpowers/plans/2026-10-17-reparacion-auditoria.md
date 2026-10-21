# Reparación de los 19 hallazgos — Implementation Plan

**Goal:** corregir los 19 hallazgos reproducibles de la auditoría y conservar el flujo DGI de diagnóstico interno.

**Architecture:** mantener Flask/Jinja/SQL Server y los estilos existentes. Autorizar por identidad y propiedad, reutilizar invariantes puras y confirmar operaciones financieras de forma atómica. Servicios pequeños para desafíos SMS, saldos de RRHH y validación contable cuando eliminen duplicación.

**Tech Stack:** Python, Flask, pyodbc, SQL Server, JavaScript DOM, CSS compilado y Playwright/Edge.

**Spec:** `docs/AUDITORIA_APLICACION_2026-10-17.md`, entregada por el usuario con autorización de reparar todos sus hallazgos. Las recomendaciones de dicho documento se contrastan con el código antes de aplicarlas.

## Global Constraints

- Conservar cambios locales anteriores; sin reset, commit, publicación ni cambio de stack.
- No usar BD habitual/Azure ni puerto 5000 para pruebas. SQL de pruebas sólo contra `localhost\\SQLDEV`, base `PanaderiaQA_Prevalidacion_20261015`, con guard obligatorio de nombre antes de escribir.
- No ejecutar migraciones productivas ni corregir datos históricos a ciegas; entregar migraciones idempotentes y verificarlas en QA.
- Mantener CSRF y el perfil fiscal pendiente como comportamiento autorizado.
- Cada corrección funcional debe tener una prueba que falle antes del cambio y apruebe después. Dobles sólo en fronteras externas; resultados esperados independientes del código.
- Ejecución continua autorizada por el usuario. Se aplica trabajo paralelo por dominios con archivos exclusivos, e integración/revisión final del conjunto.

## Review Focus

- Visitante o cliente que adivina teléfono/código: denegar acceso interno y a documentos ajenos, conservando sus propias solicitudes.
- Error al contabilizar una entrega: ningún pago ni estado confirmado; reintento sin doble cobro.
- Desafío SMS vencido, teléfono cambiado o sesión clonada: no registrar sin verificación vigente; no incluir OTP en cookies/respuestas de producción.
- Fechas superpuestas y límites de mes: asistencia/licencias sin doble conteo, vacaciones con saldo y egresos con fecha común.
- Tests o empaquetado con configuración habitual: bloquear conexiones no QA y excluir secretos del artefacto Docker.

## Tareas y propiedad de archivos

### A · Aislamiento de pruebas (16) — integración

- [x] Probar rechazo previo a conexiones no QA y rechazo de DB_NAME inesperado con conexiones sintéticas.
- [x] Incorporar guard global de pytest, fixtures reversibles de login y reescribir `tests/test_monitor.py` con datos propios/simulados, sin IDs de producción.
- [x] Verificar suite sin variable SQL (skip de integración) y con QA explícita.

### B · Autenticación (02,06,07) — agente auth

- [x] Añadir regresiones de HTML/colisión, registro sin SMS, OTP legible, caducidad/intentos/consumo y enrolamiento TOTP obligatorio/reset.
- [x] Corregir `app/auth/routes.py`, servicios propios, migración SMS idempotente, plantillas de registro/TOTP y tests exclusivos `test_auth_security.py`.
- [x] Validar imágenes mediante decodificación y nombres únicos; desafíos en servidor con ID opaco; sesión parcial de TOTP sin acceso al resto de la aplicación.
- [x] Ejecutar tests aislados y documentar migración/limitaciones.

### C · RRHH y kiosco (08–10) — agente rrhh

- [x] Reproducir doble frame, solapamiento marca/licencia/domingo y vacaciones consumidas.
- [x] Corregir `app/kiosco/routes.py`, `templates/kiosco.html`, `app/admin/routes_hr.py`, servicio RRHH y tests exclusivos.
- [x] Hacer explícita intención de salida, deduplicar fechas y compartir cálculo de saldo de vacaciones entre API y reporte, sin cambiar tasas laborales.
- [x] Ejecutar regresiones de límites y flujos válidos.

### D · Contabilidad/DGI (13–15) — agente contabilidad

- [x] Añadir regresiones de fecha compartida, asientos estructuralmente inválidos y mayor sin fila de período.
- [x] Corregir `app/admin/routes_accounting.py`, `app/services/contabilidad_service.py`, `app/services/dgi_engine.py` y validador puro compartido si procede.
- [x] Mantener interfaces compatibles para POS y pruebas; ejecutar suites puras y regresiones nuevas sin SQL real.

### E · Permisos, cotizaciones y monitor (01,03–05) — integración

- [x] Probar invitado/cliente/roles internos con CSRF real, propiedad de cotizaciones y rollback de entrega ante excepción contable.
- [x] Retirar teléfono no verificado como autorización y asociación automática; autorizar por ClienteID o token de sesión.
- [x] Renderizar textos con APIs DOM, validar URLs y retirar interpolaciones ejecutables en `templates/monitor.html`.
- [x] Prueba de navegador con payload sólo en memoria y ruta de seguimiento público conservada.

### F · Caja, mermas y manual (11,12,19) — integración

- [x] Probar tasa manipulada, merma cero/negativa y roles canónicos del manual.
- [x] Corregir `app/admin/routes_pos.py`, `app/admin/manual_admi.py`, adaptar consumidor de arqueo y añadir migración CHECK sin alterar registros históricos.
- [x] Validar conversiones con Decimal y persistir tasa autorizada.

### G · Despliegue y dependencias (17,18) — integración

- [x] Añadir `.dockerignore`, corregir base/ODBC compatibles e instalar dependencias fijadas en entorno aislado.
- [x] Consultar avisos oficiales actuales, resolver versiones compatibles y verificar `pip check`, pruebas y arranque en el entorno resultante.
- [x] Contrastar contenido de contexto sin leer/exponer secretos. Verificar build real si Docker está disponible; declarar limitación concreta si no lo está.

### H · Cierre

- [x] Revisar diffs de cada dominio e integrar sin perder estilos actuales.
- [x] Aplicar migraciones sólo QA con guard; ejecutar suite completa y cuatro verificaciones de navegador pertinentes.
- [x] Revisión independiente de seguridad/arquitectura y corrección de cualquier regresión importante.
- [x] Crear matriz 01–19 con evidencia y estado real; distinguir código corregido, verificación QA y pasos pendientes de despliegue.

## Registro de ejecución

Inicio: se releyó la auditoría adjunta y se comprobaron archivos y checkout. El usuario ya autorizó reparar todo; no se requiere otra aprobación del alcance. Se trabaja en `prueba-login`, preservando las mejoras locales anteriores y sin crear un worktree que perdería esos cambios. La auditoría histórica se conserva y el cierre se documentará por separado.

Checkpoint: código 01–15 y19 implementado con pruebas RED→GREEN por dominio. Guard QA16 y fixtures del monitor sustituidos por datos sintéticos. Suite integrada sin opt-in SQL:182 passed/61 skipped/3 avisos Flask-Login (Python3.14); 43 CSS y navegador del renderizador pendientes de repetición final. Auth implementado y pruebas locales verdes; su agente agotó cuota antes del resumen final, integración debe revisar personalmente y verificar en SQL QA la migración AuthChallenges. Código no confirmado ni publicado. Falta completar17–18, migraciones QA, pruebas SQL completas, navegador y revisión final. Python de despliegue se alinea con runtime aislado3.12.14; PyPI publica Gunicorn26.2.0 (26.2.1/26.2.2 dan404), sin avisos OSV en consulta actual; usar versión disponible verificada, no inventar pin imposible.

Cierre:252 passed/0 skipped/0 failures en entorno fijado Python3.12.14 y SQL QA;4 warnings Flask-Login. Cuatro recorridos previos de navegador y dos nuevos de seguridad pasan;43 bundles CSS verificados. Migraciones AuthChallenges y mermas/precisión de tasa idempotentes QA. Dependencias38 sin coincidencias OSV, resoluciónLinux completa, Docker no disponible (no build real). Revisión cruzada descubrió y cerró moneda de entrega y escala SQL. Impeccable detectó salto de heading corregido; tipografía/gradientes heredados conservados. Aplicación habitual/Azure/puerto5000 sin tocar; activación/migraciones allí quedan para despliegue explícito. Matriz completa en docs/REPARACIONES_AUDITORIA_2026-10-17.md.
