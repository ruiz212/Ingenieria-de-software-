# Activación y recuperación SMTP

`SMTP_ASYNC=True` persiste el evento y su entrada de outbox antes de devolver
`queued=True`; no crea hilos. **El consumidor externo es obligatorio** para
entregar esos correos. No se activa automáticamente al arrancar Flask. Si falla
la inserción de outbox, devuelve `queued=False`; el evento ya persistido permanece
en bitácora y el consumidor puede incorporarlo después. Una conexión de negocio
proporcionada por el llamador sólo encola; éste debe confirmar su transacción.

## Preparación SQL

Aplicar la migración revisada `database/04_alertas_outbox.sql` después de SQL03,
usando el migrador integral con una conexión y un nombre de base explícitos. El
script crea la cola, el estado de deduplicación y tres procedimientos, sin cambiar
el contenido forense de `BitacoraErrores`.
Los eventos nuevos de `notify_error` enmascaran claves sensibles en parámetros,
mensaje y detalle antes de persistir. Los eventos creados directamente por SQL
conservan el contenido que registró su procedimiento original; el consumidor
enmascara esos textos al construir el correo, sin reescribir la bitácora existente.

Provisionar una identidad exclusiva para el consumidor y agregar **sólo esa
identidad** al rol `db_rol_alertas_worker`. El rol permite ejecutar los tres SP;
no requiere `db_owner`, lectura de las tablas ni acceso fiscal. El principal SQL
y sus credenciales se crean mediante el procedimiento operativo del entorno;
la migración no inventa contraseñas ni concede pertenencia a usuarios existentes.

Configurar `SMTP_WORKER_CONNECTION_STRING` para esa identidad, `SMTP_ENABLED=True`,
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`/`SMTP_USE_SSL`, `SMTP_USER`, `SMTP_PASSWORD`,
`SMTP_FROM_EMAIL` y `SMTP_ALERT_RECIPIENTS`. El worker no carga `.env`; usa variables
del proceso y verifica el nombre real de la base antes de intentar entregas.

## Ejecución verificable

Una ejecución manual procesa como máximo 20 correos; en QA agregar `--qa`:

```text
python scripts/process_pending_alerts.py --once --expected-db PanaderiaQA_Prevalidacion_20261015 --batch 20 --qa
```

Este comando envía SMTP si está habilitado: en pruebas, sustituir el transporte
por un doble. La suite SQL de recuperación usa IDs propios y no llama a SMTP.
El comando imprime un JSON con `attempted`, `delivered`, `failed` y `errors`;
devuelve 0 al completar el lote, 1 ante fallos de entrega/proceso y 2 ante una
configuración o verificación inicial inválida. El límite permitido de lote es
1–100; la configuración incompleta impide arrancar.

El modo `--loop --interval 15` repite lotes seriales y requiere supervisión del
proceso. No procesar pendientes mediante una conexión de negocio abierta: el
consumidor la rechaza para evitar SMTP antes de un commit.

## App Service Python/Linux sin Docker propio

Microsoft admite WebJobs en Linux code con scripts Python. Para mantener el
trabajador activo, habilitar **Always On** en un plan compatible y configurar
`WEBSITE_SKIP_RUNNING_KUDUAGENT=false` conforme a la documentación de la plataforma.
Referencias: [plataformas de WebJobs](https://learn.microsoft.com/azure/app-service/overview-webjobs),
[creación y ejecución](https://learn.microsoft.com/azure/app-service/webjobs-create) y
[requisitos de Linux](https://learn.microsoft.com/azure/app-service/quickstart-webjobs).

1. Desplegar la aplicación y sus dependencias, incluido pyodbc y el controlador
   ODBC SQL Server. Confirmar la ruta real del código y del Python con esas
   dependencias; una compilación Oryx puede usar rutas distintas de `wwwroot`.
2. Configurar `SMTP_APP_ROOT` con esa raíz, `SMTP_WORKER_PYTHON` con el ejecutable
   Python y `SMTP_WORKER_EXPECTED_DB` con el nombre exacto de la base. Configurar
   también las variables SQL/SMTP anteriores como secretos del App Service.
3. Crear un ZIP con **sólo** `run.py` y `settings.job` de
   `scripts/webjobs/smtp_outbox/` en la raíz del ZIP. En WebJobs, cargarlo como
   tipo **Continuous**, instancia única. `run.py` arranca el consumidor explícito
   en modo loop, lote 20 e intervalo 15 segundos. Falla con código 2 si no tiene
   las rutas/nombre de base requeridos; no arranca un worker silenciosamente.
4. Revisar Logs del WebJob y hacer una prueba SMTP autorizada en el entorno.
   Verificar un evento nuevo, su estado `Sent` y la fecha de notificación. Reiniciar
   el worker y comprobar recuperación de un pendiente sintético propio. Esto aún
   debe ensayarse en el App Service real; las pruebas locales no lo certifican.

No basta con desplegar Flask ni copiar el script: **registrar y arrancar el WebJob
es un paso de activación requerido**. La presente reparación no modifica Azure.

## Semántica y operación

Cada claim usa un token y una reserva de 300 segundos compartida entre procesos.
Las transacciones SQL de reserva/confirmación son cortas; el transporte sucede
después del commit. Una caída antes de entregar deja una reserva recuperable al
expirar. Un fallo libera la clave de deduplicación y programa el reintento de la
misma fila con espera acotada hasta 300 segundos. Otros eventos de la misma clave
pueden intentarse de inmediato después del fallo.

La ventana normal de deduplicación es 300 segundos después de una entrega
confirmada. Los duplicados se conservan como `Suppressed` en outbox; no se cambia
su evidencia ni se afirma que recibieron correo. El consumidor incorpora por
lotes los errores SQL sin entrada de outbox. Un token viejo no puede confirmar ni
liberar la reserva de otro proceso.

La entrega es **al menos una vez**: si SMTP acepta el correo y el proceso cae antes
de confirmar SQL, puede repetirse después del vencimiento. Un transporte que
exceda la reserva también puede coincidir con una recuperación; el timeout de
socket es 10 segundos por operación y la reserva normal es 300 segundos. No se
promete entrega exactamente una vez. Las notificaciones explícitamente sin
persistencia sólo tienen reserva local y no se recuperan tras reinicios.
Si SQL no permite persistir, o se solicitó explícitamente `persist_in_db=False`,
la llamada intenta SMTP de forma síncrona usando los mismos cuatro cupos
limitados, sin repetir la escritura fallida ni crear hilos. Durante una caída
completa de SQL ese envío no tiene recuperación durable ni deduplicación entre
procesos; si están ocupados los cupos, el resultado informa `sent=False` y
`queued=False`. La disponibilidad de SMTP se conserva dentro de esos límites.

El número de envíos simultáneos dentro de cada proceso web está limitado a cuatro;
si se ocupan, la fila persistida queda para el consumidor. Cada consumidor externo
envía serialmente y cada lote tiene límite explícito. La cola SQL conserva el
historial durable; dimensionar y aplicar la política autorizada de retención a
sus filas terminadas y a la bitácora. No borrar registros forenses desde el worker.

Para supervisión consultar con una identidad administrativa los conteos por
`Estado`, la antigüedad de `DisponibleDesde` y las reservas `Sending` vencidas en
`seguridad.AlertasSMTPOutbox`; alertar si crecen pendientes o fallos. El JSON del
consumidor permite detectar fallos de SQL/SMTP sin exponer credenciales.
