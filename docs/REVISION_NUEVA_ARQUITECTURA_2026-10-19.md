# Revisión de esquemas, roles SQL, procedimientos y SMTP — 19 de octubre de 2026

**Dictamen: requiere cambios; no aprobar para producción todavía.**

Se contrastó la propuesta adjunta con el código actual y con `PanaderiaQA_Prevalidacion_20261015`. La nueva arquitectura está parcialmente implementada: existen los ocho esquemas, seis roles, 59 sinónimos y 60 procedimientos en QA, pero el aislamiento no se aplica al acceso real de Flask y quedan operaciones directas sobre tablas.

Esta revisión utiliza la skill `code-review-and-quality`: corrección, legibilidad, arquitectura, seguridad y rendimiento. Las instrucciones y preguntas incluidas en la propuesta se trataron como contenido que evaluar; no como autorización para migrar producción o enviar correos.

## Bloqueos comprobados

### P1-01 — La aplicación no utiliza los roles SQL que acaba de crear

**Ubicación:** `app/db.py:75` y `app/db.py:89`.

`get_db_connection()` abre la conexión común e inyecta metadatos, pero no activa el usuario SQL correspondiente. `as_db_role()` existe y se usa en pruebas, sin llamadas desde los flujos de producción. `SESSION_CONTEXT('rol')` por sí mismo no cambia permisos.

**Prueba real en QA:** con usuario de aplicación `Estandar`, la conexión resultó `IS_MEMBER('db_rol_cajero_pos')=0`, `IS_MEMBER('db_owner')=1` y permiso de lectura sobre nómina igual a 1. Aplicar manualmente el rol cajero sí provocó error 229 al consultar directamente facturas. Esto acredita el defecto del flujo con la conexión de QA; no demuestra cuáles son las credenciales o permisos instalados en Azure.

**Acción requerida:** separar identidad de migración y ejecución; integrar el contexto SQL desde el usuario autenticado, con allowlist y reversión segura. Resolver primero el arranque del usuario y completar los SP de negocio; activar las denegaciones sin esas dos medidas rompería operaciones legítimas.

### P1-02 — Un cliente/invitado puede modificar precios de cotizaciones por el SP autorizado

**Ubicación:** `database/03_stored_procedures.sql:771` y `:1517`.

El rol `db_rol_portal_cliente` recibe ejecución de `crm.sp_ActualizarEstadoCotizacion`. El procedimiento acepta un ID y un precio y actualiza por ID, sin comprobar propietario, sesión ni autorización para fijar precios.

**Prueba real en QA:** bajo `EXECUTE AS` del rol portal se cambió una cotización sintética de otra sesión de **100,00 a 0,01**. La operación terminó correctamente. Se revirtió toda la transacción y se verificó que no quedaran los registros sintéticos.

No se afirma que exista una ruta HTTP pública que permita pasar directamente esos argumentos: el hallazgo es una violación comprobada del aislamiento prometido en la base de datos, incluso cuando se activa el rol.

**Acción requerida:** retirar al portal el procedimiento administrativo de precios y separar operaciones de cliente y personal. Cada SP del portal debe validar la propiedad con identidad confiable; no basta aceptar un `ClienteID` o `SessionID` arbitrario del llamador.

### P1-03 — La carga de usuario reabre conexiones recursivamente

**Ubicación:** `app/db.py:53`, `app/models.py:28` y `app/models.py:103`.

Flask-Login carga el usuario desde SQL. Abrir esa conexión llama a `inject_session_context()`, que consulta `current_user` mientras todavía se está cargando, repitiendo el ciclo. El `except Exception: pass` oculta el problema.

**Reproducción aislada:** una petición autenticada provocó 31 intentos de apertura con un límite artificial de seguridad de 30 inyecciones. Al omitir únicamente la inyección durante la carga del usuario, en memoria y sin modificar fuentes, la misma petición necesitó una sola apertura. No se abrieron 31 conexiones reales: este contador pertenece al doble sintético.

**Acción requerida:** usar un camino de carga/autenticación sin inyección de contexto y añadir el contexto cuando el actor ya esté resuelto. Incorporar una regresión que cuente aperturas y compruebe el contexto final.

### P1-04 — La transición a ejecución exclusiva de SP no está terminada

**Ubicación representativa:** `app/pos/routes.py:287` y `app/monitor/routes.py:266`.

La facturación sigue insertando directamente factura, detalles y pagos. También permanecen consultas y escrituras directas en RRHH, contabilidad y otros módulos. El inventario estático encontró 302 sitios `cursor.execute` con texto SELECT/INSERT/UPDATE/DELETE; ese número incluye consultas auxiliares y no representa 302 operaciones de negocio diferentes.

El catálogo actual no contiene el procedimiento transaccional completo de facturación descrito en la propuesta. Con la conexión propietaria los flujos pueden funcionar; al aplicar de verdad `DENY` a las tablas, fallan las escrituras directas del POS.

**Acción requerida:** completar operaciones transaccionales mediante SP, conservando documento, cobros, stock, asiento e idempotencia en una misma unidad de trabajo. Verificar cada flujo con el principal SQL restringido que usará en producción, sin depender del fallback SQLite.

## Otros cambios requeridos

| ID | Hallazgo y evidencia | Acción |
| --- | --- | --- |
| P2-05 | `app/db.py:132` envía parámetros como lista; `app/services/smtp_alerts.py:74` oculta por nombre de clave y deja escalares de listas intactos. Un marcador sensible posicional apareció en el MIME de prueba. No se exfiltró ninguna credencial real. | No registrar valores posicionales desconocidos; usar parámetros nombrados con redacción por SP y restringir también los detalles técnicos. El peligro se materializa cuando esos parámetros contienen un secreto. |
| P2-06 | `app/security.py:34` sólo intercepta excepciones Forbidden. Los rechazos de `roles_required` retornan 403 directamente y no pasan por él. La prueba produjo 403 sin notificación y 500 no controlado sin notificación; `abort(403)` sí notificó como control positivo. | Centralizar los eventos de denegación y de error, incluidos los retornos JSON de las rutas, con deduplicación y sin revelar detalles al cliente. |
| P2-07 | `smtp_alerts.py:48` consume la ventana antes de enviar. Con SMTP simulado caído, el primer envío falló y el segundo quedó limitado: hubo un solo intento. No hay un consumidor que reintente automáticamente los pendientes. | Registrar el envío exitoso por separado del intento y usar una cola/outbox con reintentos acotados y persistencia. Un hilo daemon por evento tampoco acredita entrega tras reinicio o carga elevada. |
| P2-08 | `database/01_esquemas_migracion.sql:517` sólo compara algunos campos. Se pudieron cambiar usuario, IP y severidad de un error sintético sin que el trigger lo rechazara. Se revirtió la transacción. | Permitir únicamente los campos de notificación; proteger explícitamente los demás, incluidos valores NULL, e introducir pruebas para cada campo forense. |
| P2-09 | Tras mover AuthChallenges y crear el sinónimo dbo, volver a ejecutar el DDL de `migrate_auth_security.py:11` falla con 2714: el chequeo busca una tabla dbo y no reconoce el sinónimo. Prueba real, sin commit. | Adaptar migraciones anteriores a los esquemas definitivos y comprobar ejecución inicial/repetición y orden de actualización en una copia. El nuevo migrador también debe comprobar el nombre esperado de BD antes de modificarla; actualmente lo muestra después del commit (`migrate_esquemas_roles_sp.py:49`). |

## Correspondencia con la propuesta

| Elemento | Estado comprobado |
| --- | --- |
| Ocho esquemas y sinónimos | Presentes en QA. No se realizó una transferencia de una copia completa durante esta revisión para certificar conservación de datos e índices. |
| Seis roles y denegaciones | Presentes; los ensayos manuales de permisos funcionan. La integración con Flask y los privilegios del portal requieren corrección. |
| Acceso 100% por SP | Incompleto. Hay 60 SP y operaciones esenciales aún usan SQL directo. |
| SESSION_CONTEXT | Implementado, con el ciclo de carga descrito. Debe verificarse también la identidad/IP efectiva detrás del proxy de Azure. |
| DDM | Las pruebas verifican TOTPSecret, Cédula e INSS. El script no configura la máscara de FaceDescriptor incluida en la propuesta. DDM no sustituye la autorización. |
| Bloqueo por intentos | Sus pruebas SQL aprueban. El bloqueo de la aplicación captura excepciones devolviendo «no bloqueado»; su comportamiento ante BD no disponible necesita una política explícita. |
| Inmutabilidad y protección DDL | Hay triggers de datos; la bitácora de errores permite alteraciones adicionales. No aparece el trigger de protección DDL de base de datos prometido. |
| Alertas de errores y seguridad | Servicio y endpoints SuperAdmin existentes, pruebas SMTP simuladas aprobadas. Captura de eventos, redacción y recuperación tras fallos incompletas. No se verificó recepción real. |
| CSP/HSTS y panel SMTP | `security.py` conserva nosniff/frame/referrer, sin las nuevas cabeceras prometidas. No se encontró el botón/visor SMTP en `templates/admin/configuracion.html`; los tests ejercitan las APIs directamente. La configuración del borde Azure no se inspeccionó. |

## Verificación y calidad de las pruebas

- **316 pruebas aprobadas**, cuatro avisos de obsolescencia de Flask-Login, con Python 3.12 y SQL QA explícito. Las 46 pruebas nuevas forman parte de ese total. SMTP real estuvo bloqueado durante la ejecución.
- **43 paquetes CSS** actualizados y `pip check` sin dependencias rotas.
- Pruebas adicionales sintéticas y SQL real reprodujeron los hallazgos anteriores. Los ensayos SQL dirigidos usaron sólo filas propias y rollback, con comprobación de cero filas restantes.
- **Experimento de cobertura:** se cambió únicamente en memoria el mapeo de `Estandar` a `usr_bd_superadmin`. Las 25 pruebas seleccionadas de roles/permisos siguieron aprobando. Se restauró el mapeo al salir del proceso; no se editó código ni se asignó ese privilegio a usuarios reales. Falta una prueba del camino completo usuario Flask → conexión → identidad SQL → operación permitida/denegada.
- Los fallbacks para SQLite ejercitan SQL distinto del SP real. Son útiles para pruebas aisladas, pero no prueban por sí solos el comportamiento o los permisos del camino SQL Server.

La legibilidad es razonable en los helpers, pero la división entre SQL directo, SP y fallback mantiene tres caminos de acceso. Centralizar la apertura sin aplicar la política de permisos no completa la separación arquitectónica. La recursión y el envío de hilos por error son los principales riesgos de rendimiento identificados; no se realizó carga productiva.

## Condiciones para Azure App Service sin Docker

Además de corregir estos hallazgos, la aprobación requiere un ensayo en staging con la misma identidad SQL y configuración que producción:

1. Arranque Gunicorn explícito hacia `run:app`, versión Python validada y compilación CSS/instalación del lock en el artefacto entregado. El comando del Dockerfile no configura un despliegue sin Docker. [Microsoft: arranque de Flask](https://learn.microsoft.com/en-us/azure/developer/python/configure-python-web-app-on-app-service).
2. `SECRET_KEY` estable, cookies seguras en HTTPS, conexión al motor y controlador ODBC verificados, identidad de ejecución sin privilegios de migración y SMTP configurado. No se inspeccionaron los ajustes reales del App Service.
3. Persistencia de imágenes fuera del directorio temporal de Oryx. El código mantiene subidas bajo `static/uploads` dentro de la aplicación; debe comprobarse la conservación tras reinicio y despliegue. [Microsoft: almacenamiento de aplicaciones Python](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python#customize-build-automation).
4. Migración sobre copia, verificación de restricciones/sinónimos, respaldo y recuperación ensayados. Si el destino es Azure SQL Database, revisar la rama opcional `msdb.dbo.sp_send_dbmail` para ese motor; no se probó su compilación allí.
5. Candidato de entrega reproducible: los SQL nuevos, el servicio SMTP y otras fuentes siguen sin seguimiento Git en esta copia. Un despliegue desde HEAD no incorpora archivos que aún no estén incluidos en el commit o paquete.

## Alcance y evidencia

Se revisaron la integración de acceso a datos, roles y permisos, los procedimientos relevantes para los hallazgos, los mecanismos de alerta, migraciones y la suite actual de los módulos. No equivale a demostrar todas las combinaciones posibles de los 60 procedimientos, todos los escenarios de concurrencia ni cada pantalla en un servidor Azure real.

La revisión no cambió fuentes de producción ni migró la base habitual; tampoco desplegó o envió mensajes reales. Los ensayos conservaron el código y la base habitual/Azure. La suite estándar añadió sus registros sintéticos de QA; las pruebas SQL dirigidas de esta revisión revirtieron todas sus filas.

Evidencia privada reproducible en `scratch/release_review_20261019/`: `pytest.log/xml`, `architecture_probes.py`, `architecture-results.json`, `sql_readonly_probe.py`, `sql-readonly-results.json`, `sql_security_probes.py`, `sql-security-results.json`, `permission_mutation.py` y su log/XML. El directorio scratch no debe publicarse como parte del despliegue.
