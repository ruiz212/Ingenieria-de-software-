# Revalidación de correcciones — 19 de octubre de 2026

**Dictamen: las correcciones mejoran la implementación, pero todavía hay bloqueos para producción.**

Se volvió a revisar el código actual mediante `code-review-and-quality` y `verification-before-completion`, contrastando los hallazgos anteriores con pruebas nuevas. Esta revisión distingue pruebas generales aprobadas de fallos reproducidos mediante ensayos específicos. No se modificó código de la aplicación ni se desplegó o migró producción.

## Verificación realizada

- **327 pruebas aprobadas**, cero fallos y cuatro advertencias de obsolescencia de Flask-Login. Ejecución nueva con Python 3.12 y conexión explícita a `PanaderiaQA_Prevalidacion_20261015`; SMTP real bloqueado. Evidencia: `scratch/architecture_recheck_20261019_2/pytest.log` y `pytest.xml`.
- **50 consultas HTTP de páginas/APIs con cinco roles sintéticos** contra SQL QA real: 49 respuestas 200 y una redirección 302 del rol Admin al intentar consultar auditoría reservada a SuperAdmin. Se probaron dashboard, estadísticas, RRHH, contabilidad, DGI, inventario, producción, catálogo, usuarios, configuración, arqueos, POS, cotizaciones y monitor según rol. Esto comprueba carga y consultas, no todos los formularios ni cada operación de escritura.
- **340 procedimientos presentes en QA**. La conexión normal de un usuario Estandar ahora resulta `usr_bd_cajero_pos`, sin pertenencia a `db_owner` y sin permiso SELECT sobre nómina.
- **43 paquetes CSS verificados** mediante `scripts/build_css.py --check`; `pip check` sin dependencias rotas.
- Pruebas de navegador con Edge/Playwright, activos actuales y datos sintéticos reprodujeron el XSS del POS y el defecto del visor de errores. En el ensayo XSS se aplicó también la CSP actual.
- Ensayos SQL dirigidos crearon únicamente cotizaciones/facturas propias en QA; se hizo rollback y se comprobó **cero filas propias restantes**. La suite general puede registrar sus eventos sintéticos habituales en QA.
- La nueva prueba del mapeo de roles detecta una mutación incorrecta: al cambiar **sólo en memoria** Estandar a `usr_bd_superadmin`, falla la aserción de identidad SQL. El mapeo se restaura al salir del proceso. Es una mejora respecto de la cobertura anterior; falta cubrir el fallo de impersonación descrito abajo.
- No se encontraron archivos Python/SQL de aplicación, base de datos o tests modificados después de finalizar la ejecución general en esta revisión.

## Bloqueos comprobados

### R1 · P1 — El fallo de activación de rol devuelve una conexión privilegiada

**Ubicación:** `app/db.py:197–211`, especialmente el `except Exception: pass` de la línea 203.

El camino normal ya activa el rol. Sin embargo, un error de `EXECUTE AS` se ignora y la función devuelve la conexión original. Se simuló únicamente el rechazo de impersonación, conservando una conexión SQL real a QA: con usuario Flask Estandar, el resultado fue `USER_NAME() = dbo`, `IS_MEMBER('db_owner') = 1` y permiso SELECT sobre nómina igual a 1. En la misma prueba sin fallo, los valores fueron cajero, 0 y 0 respectivamente.

**Impacto:** una falta de permiso de impersonación, un usuario SQL ausente u otro error de activación elimina silenciosamente el aislamiento previsto.

**Corrección requerida:** cerrar la conexión y propagar un error controlado cuando no se pueda establecer la identidad requerida; no devolverla al llamador. Diferenciar explícitamente el acceso limitado de autenticación/migración del acceso de negocio y usar una identidad de ejecución con privilegios mínimos. Añadir la prueba de activación fallida además de la prueba normal.

**Evidencia:** `role_probe.py`, `role-results.json` en el directorio de evidencias de esta revisión. No se leyeron valores de nómina.

### R2 · P1 — XSS almacenado al mostrar la imagen de una cotización

**Ubicación:** `static/js/pos.js:145`; entrada en `app/pos/routes.py:489–524`.

`ruta_imagen_referencia` se admite desde la solicitud y luego `c.ruta_imagen` se inserta sin codificar en un atributo `href` construido con `innerHTML`. Un valor con comillas puede cerrar el atributo e introducir una etiqueta con un manejador de evento.

Se comprobó por separado que el procedimiento real acepta y devuelve ese valor bajo el rol portal, usando una cotización sintética con rollback. En Edge, el JavaScript actual del POS ejecutó el marcador `window.__quoteXSS=true` al abrir solicitudes, incluso con la CSP actual, que permite eventos inline. El navegador usó una respuesta API sintética y bloqueó tráfico externo; no se insertó el ataque en datos de operación.

**Corrección requerida:** validar referencias como rutas de subida autorizadas o URLs con protocolo y origen permitidos; construir el enlace con APIs DOM y asignar su texto/atributos sin interpolar HTML. Probar comillas, etiquetas y protocolos no admitidos. Endurecer CSP después de adaptar los eventos inline.

**Evidencia:** `sql-security-results.json`, `xss_probe.mjs`, `xss-result.json`.

### R3 · P1 — Todavía se puede entregar una factura anulada

**Ubicación:** `app/monitor/routes.py:251–278`; `database/03_stored_procedures.sql:3239` y `:3490`.

Los procedimientos que buscan el encargo y cambian su estado no excluyen `EstadoFiscal = 'Anulada'`. La ocultación de anuladas en el listado del monitor no protege la operación por código de seguimiento.

**Prueba SQL real:** el rol Operativo encontró una factura sintética anulada y cambió su encargo de Listo a Entregado. Todo se revirtió. La ruta completa, probada con el adaptador SQLite existente y contabilidad simulada, respondió 200 y registró el cobro y sus líneas contables para una factura anulada.

**Corrección requerida:** verificar el estado fiscal dentro de la transacción, bloquear el registro fiscal relevante y condicionar también el UPDATE a que la factura continúe emitida. Rechazar sin cobro, asiento ni cambio de estado cuando esté anulada. Cubrir la carrera entre anulación y entrega.

**Evidencia:** `sql-security-results.json`, `probe_delivery.py`, `delivery-results.log`.

### R4 · P1 — Los saldos cobrados en otro turno quedan fuera de su arqueo

**Ubicación:** `app/monitor/routes.py:307–319`; `app/admin/routes_pos.py:160–172`; `database/03_stored_procedures.sql:4338–4349` y `:4626`.

El cobro de entrega guarda FacturaID pero no identifica el turno que recibe el dinero. El cálculo de caja suma por `Facturas.TurnoID`, es decir, el turno de emisión.

**Reproducción:** factura emitida en turno 7, turno 7 cerrado, turno 8 abierto y cobro de C$50 al entregar. La entrega responde 200, los pagos siguen asociados por factura al turno 7 y el arqueo del turno 8 muestra **C$0 de efectivo del sistema**. La reproducción ejecuta las rutas actuales mediante el adaptador SQL sintético; el SP nuevo conserva la misma agrupación por turno de factura, comprobada en su definición.

**Corrección requerida:** registrar turno receptor, usuario y fecha de cada movimiento de caja, y calcular arqueos desde esos movimientos. Exigir un turno receptor abierto para cobros que lo requieran y definir el tratamiento de cobros fuera de caja. Probar anticipos y saldos en turnos y días diferentes.

### R5 · P1 — El rol Operativo no tiene permisos necesarios para contabilizar la entrega

**Ubicación:** `database/03_stored_procedures.sql:4970–5003`; `app/services/contabilidad_service.py:265–274`.

La ruta permite al rol Operativo entregar y cobrar saldos. `contabilizar_cobro_encargo()` llama a `crear_asiento()`, que consulta `seguridad.sp_ObtenerConfiguracionGlobal` y registra la auditoría mediante `fiscal.sp_RegistrarBitacoraFiscal`. El primer SP no está concedido a producción; el esquema fiscal tiene DENY EXECUTE.

**Prueba SQL real:** ejecutar la lectura de configuración como Operativo devuelve error 229; el permiso EXECUTE del SP de auditoría fiscal vale 0. Son dependencias obligatorias del asiento, de modo que una entrega con saldo que llegue a ese tramo falla y revierte. Cargar el monitor con 200 no verifica este camino.

**Corrección requerida:** alinear la operación autorizada con sus dependencias mediante permisos mínimos o un procedimiento de negocio que encapsule cobro y auditoría. Evitar conceder acceso fiscal general. Si Operativo no debe cobrar, restringir esa acción en servidor e interfaz. Añadir integración de una entrega con saldo bajo la identidad SQL real de ese rol.

## Hallazgos adicionales

### R6 · P2 — La IP de auditoría puede ser elegida mediante una cabecera

`app/db.py:86–95` y `app/services/smtp_alerts.py:65–67` usan directamente el primer elemento de `X-Forwarded-For`. En una petición sintética con REMOTE_ADDR diferente, una cabecera arbitraria sustituyó tanto la IP de contexto SQL como la del correo. La aplicación configura ProxyFix para protocolo/host, sin una política equivalente para esa selección manual de IP.

Definir los proxies de confianza y extraer la dirección desde la cadena validada; no considerar confiable el primer salto suministrado por cualquier cliente. Verificar el comportamiento real del borde Azure antes de fijar el número de saltos. Evidencia: `alert-results.json`.

### R7 · P2 — La recuperación SMTP está incompleta y la deduplicación tiene una carrera

`app/services/smtp_alerts.py:40–55` y `:434–440` comprueban la ventana y registran el envío en secciones distintas. Dos trabajadores simultáneos del mismo error atravesaron la comprobación y ambos enviaron: **2 envíos simulados, 0 bloqueados** dentro de la misma ventana. La caché tampoco se comparte entre procesos.

El reintento después de un fallo SMTP secuencial ya está corregido. Ahora existe `retry_pending_alerts()`, pero no se encontró un consumidor que lo programe o invoque en la aplicación; definir la función no recupera por sí mismo un envío fallido. Además continúa creándose un hilo daemon por aviso antes de deduplicarlo.

Completar una cola limitada con reserva atómica, liberación de reserva al fallar y un consumidor de pendientes verificable. Si hay varios workers, coordinar la deduplicación entre ellos. Evidencia: `alert_probe.py`, `alert-results.json` y búsqueda de referencias a `retry_pending_alerts`.

### R8 · P2 — El visor de errores no muestra mensaje, usuario ni rol reales

**Ubicación:** `templates/admin/configuracion.html:332–334`; contrato en `app/admin/routes_users.py:256–259`.

La API devuelve `usuario`, `rol` y `mensaje`; la plantilla lee `username`, `rol_aplicacion` y `mensaje_error`. En el navegador, una respuesta con usuario y mensaje sintéticos válidos produjo «Anónimo (N/A)» y una celda de mensaje vacía.

Unificar el contrato y representar los campos con texto seguro; añadir una prueba que compruebe el contenido visible del panel usando la estructura real de la respuesta. Evidencia: `panel_probe.mjs`, `panel-results.json`.

## Estado de los nueve hallazgos de la revisión anterior

| Hallazgo anterior | Estado en esta revisión |
|---|---|
| P1-01: no se activaban roles SQL | Corregido en el camino normal; **parcial** por R1. La prueba nueva sí detecta un mapeo equivocado. |
| P1-02: el portal podía modificar precio ajeno | **Corregido para el vector probado**: DENY efectivo y pruebas de rechazo aprobadas, incluido ensayo SQL dirigido. Esto no certifica todos los SP del portal. |
| P1-03: carga recursiva del usuario | **Corregido en las pruebas actuales** mediante carga sin inyección y guarda de autenticación. |
| P1-04: SQL directo impedía usar roles restringidos | Conversión sustancial a SP, 340 presentes y prueba AST aprobada. Lecturas de pantallas funcionan; **no cerrar la integración de escritura** por R5. El test AST por sí solo no verifica contratos, transacciones ni permisos. |
| P2-05: secretos posicionales en alertas | **Corregido para los casos de regresión probados**; pruebas de enmascarado aprobadas. |
| P2-06: faltaban alertas de 403 y 500 | **Corregido en los ensayos actuales**: 403 devuelto y excepción no controlada 500 notifican una vez. |
| P2-07: SMTP fallido consumía la ventana | **Corregido el reintento secuencial**; recuperación operativa y concurrencia pendientes en R7. |
| P2-08: metadatos de errores modificables | **Corregido para las columnas de regresión comprobadas**; suite SQL aprobada. |
| P2-09: migración auth incompatible con sinónimos | **Corregido en QA**; reejecución aprobada. El migrador integral verifica además el destino antes de ejecutar los lotes. No se ejecutó esta migración sobre producción. |

Se añadieron también CSP/HSTS, máscara de FaceDescriptor, trigger de protección DDL y panel SMTP en el código. La existencia de esos mecanismos no cierra los fallos descritos ni sustituye un ensayo en el entorno de destino.

## Límites y despliegue

No se certifica todavía Azure App Service sin Docker: no se inspeccionó su configuración real ni se ensayaron arranque Linux, identidad SQL productiva, reinicio con conservación de imágenes, entrega SMTP o recuperación de respaldos. El código conserva subidas dentro de `static/uploads`; deben verificarse persistencia y ruta de almacenamiento en el destino. `SECRET_KEY` y cookies seguras siguen dependiendo de variables de entorno que no se comprobaron en Azure.

El árbol de trabajo contiene numerosas modificaciones y archivos nuevos sin seguimiento. Esta revisión evalúa los archivos locales; desplegar sólo HEAD no reproduce necesariamente ese estado. No se hicieron commits, reinicios del servidor habitual, cambios de permisos productivos ni envíos de correo reales.

Las pruebas están en `scratch/architecture_recheck_20261019_2/`. El informe anterior se conserva como evidencia histórica y sus cifras no se presentan como validación del estado actual.
