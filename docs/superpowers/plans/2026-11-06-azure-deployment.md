# Reparación del despliegue Python en Azure

**Objetivo:** publicar fuente Python con compilación Oryx, comprobar el arranque y fusionar en `main` tras validación.

**Autorización:** el usuario solicita reparación, subida a GitHub y merge. La cancelación del último despliegue fue manual y no se considera causa del incidente. Sin migraciones ni cambios de datos.

**Evidencia:** el artefacto remoto contiene `run.py` en la raíz y tiene CRC correcto. Azure informa importación fallida de `run`, sin manifiesto ni entorno Oryx. El workflow usa OneDeploy para un ZIP que no contiene dependencias. Windows local no dispone de Linux/WSL ni Docker; validar Gunicorn en CI Linux. Base: `main` y `origin/main` coinciden en `393099b`. Suite inicial: 438 aprobadas, 168 omitidas sin conexión QA.

**Arquitectura:** mantener Flask y el paquete explícito existente. Usar el endpoint Kudu ZipDeploy para compilar fuentes y esperar el resultado real, verificando manifiesto Oryx y respuesta de login. Reutilizar el publish profile secreto del workflow sin exponerlo ni versionarlo. Conservar las optimizaciones locales previas.

- [x] Añadir pruebas que fallen para rechazar paquetes incompletos y comprobar el cliente ZipDeploy, fallos remotos y protección de credenciales.
- [x] Incluir `.deployment` con compilación habilitada; validar archivos requeridos antes de escribir el ZIP; implementar despliegue con espera acotada y comprobación Oryx/HTTP.
- [x] Ejecutar CI también en PR; comprobar importación y arranque Gunicorn desde el ZIP extraído fuera del checkout; serializar despliegues y usar ZipDeploy en producción.
- [ ] Ejecutar suite sin SQL operativo, comprobar CSS, revisar diff y exclusión de secretos; subir rama, abrir PR, esperar CI Linux, fusionar y observar el resultado de despliegue.

**Límites:** no certificar SQL, WhatsApp ni credenciales sin pruebas específicas; no publicar `.env`, `scratch/` ni archivos privados. No asumir que éxito de transporte equivale a aplicación lista.

## Registro de verificación local

- 455 pruebas aprobadas, 168 omitidas; 46 paquetes CSS vigentes.
- ZIP real extraído en carpeta temporal: importación y páginas públicas aprobadas
  sin SQL ni modelos faciales. Arranque Gunicorn reservado a CI Linux.
- `pip check` global detecta conflictos de protobuf con paquetes Google externos
  a los requisitos del proyecto. No se modifica el Python global; CI crea un
  entorno virtual limpio y ejecuta su propio `pip check`.
- Revisión: transporte HTTPS y credenciales limitadas a SCM, redirecciones
  deshabilitadas, espera acotada, fallos remotos bloquean el éxito; datos y reglas
  de negocio conservados. Se incluye `gunicorn.conf.py` en el contexto Docker.
