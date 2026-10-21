# Correcciones de la auditoría — 17 de octubre de 2026

> **Seguimiento del 18 de octubre:** este cierre corresponde a los 19 hallazgos enumerados, no a una validación exhaustiva de toda la aplicación. Las capturas del usuario revelaron problemas operativos adicionales; sus correcciones, pruebas y la sospecha no confirmada sobre la navegación se documentan en [la revisión operativa](REVISION_OPERATIVA_2026-10-18.md).

Los 19 hallazgos de la [auditoría original](<C:/Ingenieria de software/panaderia_amada/docs/AUDITORIA_APLICACION_2026-10-17.md>) tienen correcciones en el código y regresiones verificadas. La auditoría original se conserva como evidencia del estado anterior.

**Alcance de activación:** las migraciones se aplicaron y repitieron en `PanaderiaQA_Prevalidacion_20261015`. La base habitual/Azure y el servidor habitual del puerto 5000 no se modificaron durante esta reparación. Para activar el cambio allí hay que aplicar las dos migraciones y reiniciar el proceso con el entorno de dependencias fijado. No se publicaron cambios ni se hicieron commits.

## Matriz de cierre

| ID | Corrección implementada | Evidencia de regresión |
| --- | --- | --- |
|01|Invitado y Cliente excluidos del monitor interno y su API de escritura; roles de personal conservados.|`test_monitor.py`: matriz de roles con CSRF real. Navegador: invitado público recibe403 al leer/escribir.|
|02|Perfil decodificado con Pillow, convertido a JPEG sin metadatos/contenido añadido, tamaño limitado y nombre UUID exclusivo; limpieza si falla INSERT.|`test_auth_security.py`, `test_uploads.py`: HTML renombrado rechazado, imágenes reales, colisiones, bytes añadidos y rollback.|
|03|Una sola política por ClienteID o token privado para cotizaciones sin asignar. Se eliminaron permisos y asociación por teléfono; un token antiguo no concede documentos ya asignados a otro cliente.|`test_quote_ownership.py`: 13 casos sobre consultas reales traducidas a SQLite, incluidos teléfono ajeno y sesión antigua.|
|04|Tarjetas construidas con nodos/textContent, URLs http/https y listeners que no interpolan códigos en atributos ejecutables.|`monitor_security.mjs`: 5 comprobaciones en Edge con valores hostiles sólo en memoria; sin ejecución de HTML.|
|05|Entrega, pago y asiento comparten transacción; excepción contable provoca rollback y409. Reintento idempotente no duplica cobro.|`test_monitor.py`: fallo contable conserva estado/pagos; entrega válida y reintento. Caso adicional entrega USD→arqueo ejecuta ambas rutas y SQL en SQLite.|
|06|SMS almacenado en SQL con HMAC, cookie con identificador opaco,10 min de vigencia,5 intentos, consumo único transaccional y60 s entre envíos al mismo número. Registro exige teléfono normalizado y desafío comprobado.|`test_auth_security.py` y `test_security_sql.py`: sesiones clonadas, expiración, teléfono distinto, reenvíos y concurrencia de intentos en SQL QA. Frontend SMS y429 comprobados con proveedor simulado.|
|07|Enrolamiento TOTP restringido antes de crear sesión completa, estado compartido en SQL, caducidad/intentos y vínculo con configuración actual. Reset invalida verificaciones pendientes; fallo al leer política no desactiva el requisito.|Pruebas de rutas y servicio; enrolamiento/reset real sobre un usuario sintético en SQL QA. Ningún acceso completo antes de confirmar.|
|08|Entrada y salida explícitas e idempotentes; mínimo60 s para salida, bloqueo de empleado/asistencia en mismo orden. UI pausa hasta una nueva selección.|`test_kiosco_regressions.py`: casos públicos/administrativos y JavaScript real en VM. Edge con cámara sintética: ninguna petición antes de elegir y una sola marca por selección.|
|09|Ausencias: fechas laborales dentro del empleo menos unión de asistencias/licencias. Domingos y solapamientos no restan dos veces.|`test_hr_regressions.py`: fechas coincidentes, domingos, período y límites de contratación.|
|10|API y reporte comparten cálculo de liquidación; descuentan DiasOtorgados de vacaciones transcurridas hasta el corte, sin saldo negativo.|`test_hr_regressions.py`: vacaciones consumidas, futuras, parciales y anteriores al empleo; igualdad API/reporte. Tasas previas conservadas.|
|11|Arqueo ignora tasa del navegador, obtiene tasa autorizada, usa Decimal y guarda 6 decimales. Entrega USD conserva su importe nacional con MonedaRegistro=NIO y tasa aplicada.|`test_cash_controls.py`, `test_delivery_cash_currency.py` y SQL QA que persiste 36.624345 sin redondearlo a 4 decimales.|
|12|Cantidad de merma validada como entero positivo y motivo permitido; restricción CHECK en SQL. Migración rechaza históricos incompatibles sin modificarlos.|Pruebas de cero/negativo/fracción/NaN/bool, caso válido y rechazo real por CK_Mermas_CantidadPositiva en QA.|
|13|Una fecha de negocio capturada una vez se inserta en egreso y se transmite al asiento.|`test_accounting_regressions.py`: límite de mes y compatibilidad de llamadores.|
|14|Validador puro compartido: mínimo 2 líneas, un solo lado positivo por línea, importes finitos/no negativos, total positivo y Debe=Haber. Motor DGI 1.2 invalida revisiones antiguas mediante el flujo existente.|`test_dgi_engine.py`: estructuras inválidas, precisión, determinismo e invalidación de motor 1.1.|
|15|Mayor consulta límites de fecha aunque no exista fila de período, conservando saldo anterior sin crear períodos desde GET.|Pruebas de octubre, febrero bisiesto, diciembre y saldo anterior con/sin movimientos.|
|16|pytest no carga.env; Config usa sólo TEST_DB_CONNECTION_STRING explícita. Guard previo y comprobación DB_NAME, restauración del loader entre tests. Monitor usa datos sintéticos propios.|`test_qa_safety.py`: 6 casos; suite sin opt-in omite SQL. Suite completa QA sin errores ni omisiones.|
|17|Docker usa contexto por lista de permitidos, excluye secretos/datos/adjuntos, comprueba que no hay.env/scratch/.git, fija Debian bookworm y repositorio ODBC correspondiente.|Revisión de reglas y Dockerfile; instalación y resolución Linux del lock verificadas. **No hay Docker disponible para construir/arrancar una imagen real aquí.**|
|18|Dependencias directas y transitivas fijadas; entorno separado Python 3.12; Flask/Flask-WTF/Gunicorn actualizados. Herramientas de tests incluidas explícitamente en requirements-dev.|Instalación limpia, pip check, suite completa en ese entorno y resolución de wheels Linux. Consulta OSV de 38 paquetes: 0 coincidencias conocidas en el momento de revisar.|
|19|Manual accesible por Admin/SuperAdmin y contenido operativo en el layout existente.|Pruebas de ambos roles y respuesta200 con contenido, sin página vacía.|

## Verificación integrada

- **252 pruebas aprobadas**, sin errores ni omisiones, en SQL QA y Python 3.12.14 con las versiones del lock. Cuatro avisos de obsolescencia de `datetime.utcnow()` proceden de Flask-Login 0.6.3; no se silenciaron ni se parcheó la biblioteca.
- **43 paquetes CSS** generados y comprobados. Se conservaron los cambios de diseño previos; se ajustaron sólo los controles nuevos de registro/kiosco y la visibilidad/jerarquía de los pasos.
- Cuatro recorridos existentes de Edge aprobados: navegación/foco/confirmaciones, tienda/carrito sin enviar pedido, movimiento normal/reducido y carga de 18 páginas. Cobertura de 320–1440 px según escenario.
- Dos recorridos adicionales: renderizador del monitor frente a HTML hostil y flujos de seguridad de registro/kiosco/invitado. Sin SMS real, cámara real, registro de cliente ni marca de asistencia en las pruebas de navegador.
- Migraciones de autenticación y seguridad financiera repetidas dos veces en QA para comprobar idempotencia. Los tests SQL usan registros propios y limpian sus usuarios/desafíos; no toman el primer pedido existente.
- Revisión independiente encontró dos problemas de integración adicionales (moneda de la entrega y precisión persistida de la tasa); ambos se reprodujeron antes de corregirlos y sus nuevas regresiones aprueban.
- Mutaciones aisladas en memoria comprobaron que las nuevas pruebas detectan reglas contables y la ventana mínima del kiosco. No se alteraron temporalmente fuentes compartidas.

La primera ejecución en el entorno limpio encontró que el lector independiente de Excel `openpyxl` faltaba en las dependencias de desarrollo; se añadió y se repitió la suite. Los resultados parciales y los casos RED permanecen como evidencia, no como fallos abiertos del cierre.

El detector Impeccable se ejecutó una vez. No resuelve llamadas Jinja `css_url`, por lo que su jerarquía tipográfica calculada desde el HTML sin renderizar no era representativa; se inspeccionaron capturas reales. Se corrigió el salto h1→h3 del registro. Sus observaciones sobre Inter y gradientes ya existentes del kiosco se conservaron como decisiones del diseño anterior, fuera de esta reparación; no se añadió un rediseño.

Evidencia privada: [scratch/remediation_20261017](<C:/Ingenieria de software/panaderia_amada/scratch/remediation_20261017/>), incluyendo XML/logs de pytest, resultados y capturas de navegador, auditoría de dependencias y resolución Linux. Ese directorio está ignorado por Git y contiene datos de acceso sintéticos; no publicarlo.

## Instalación y activación

Usar Python 3.12 en un entorno virtual nuevo:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pip check
```

Para ejecutar sólo la aplicación, `requirements.lock` contiene las dependencias de producción; `requirements-dev.txt` añade pytest y el lector independiente de Excel. Docker utiliza Python 3.12/bookworm y ese mismo lock. Antes de publicar, construir y comprobar la imagen en un equipo con Docker; aquí sólo se verificó la resolución Linux, no un arranque Linux/Gunicorn.

Las siguientes migraciones necesitan una conexión y un nombre de BD explícitos. Revisar el destino y conservar respaldo antes de ejecutarlas sobre una base habitual. Ninguna lee .env por su cuenta:

```powershell
python scripts/migrate_auth_security.py --connection-env DB_CONNECTION_STRING --database NOMBRE_EXACTO_DE_LA_BASE
python scripts/migrate_inventory_safety.py --connection-env DB_CONNECTION_STRING --database NOMBRE_EXACTO_DE_LA_BASE
```

La primera crea AuthChallenges y su índice para SMS/TOTP. La segunda añade el CHECK positivo de mermas y amplía TipoCambioUsado a DECIMAL(12,6), sin recalcular históricos. Si detecta mermas incompatibles, detiene la transacción: sus orígenes deben revisarse, no borrarse a ciegas. La tabla AuthChallenges es necesaria antes de habilitar los nuevos flujos SMS/TOTP.

Después, reiniciar el servidor con las dependencias nuevas. Twilio debe tener credenciales y remitente válidos: sin proveedor disponible el sistema informa que SMS no está disponible; no muestra códigos ni habilita un registro sin verificar. Para pruebas completas, definir TEST_DB_CONNECTION_STRING a una base cuyo nombre empiece por PanaderiaQA_; sin esa variable la suite no abre la conexión habitual.

## Límites conservados

El perfil fiscal pendiente y los diagnósticos internos no se convierten en presentación oficial DGI. No se validaron tasas laborales/fiscales nuevas. Vacaciones pagadas fuera del sistema, sin licencia o registro equivalente, no pueden inferirse: el saldo descuenta las licencias existentes, y no se inventa un historial externo.

No se ejecutaron carga productiva, cámara física, SMS real ni pruebas contra Azure. No se revirtieron posibles cambios de la primera ejecución de la auditoría histórica: no había evidencia suficiente para atribuirlos ni una restauración segura que aplicar.
