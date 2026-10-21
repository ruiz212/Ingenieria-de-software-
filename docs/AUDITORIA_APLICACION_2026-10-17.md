# Auditoría de la aplicación — 17 de octubre de 2026

**Dictamen: requiere correcciones antes de usarla con datos reales o publicarla.** Se identificaron 19 hallazgos: 5 P1, 13 P2 y 1 P3. Las pruebas existentes aprueban, pero no cubren varios de los escenarios adversos reproducidos en esta revisión.

Se aplicó `code-review-and-quality` en cinco ejes: funcionamiento, legibilidad, arquitectura, seguridad y rendimiento. Se revisó el estado actual del proyecto, incluidos los cambios locales anteriores; los hallazgos no se atribuyen automáticamente a esos cambios. Esta revisión no modifica la implementación ni repara datos.

## Hallazgos de prioridad alta

### 01 · P1 · Un invitado puede leer y modificar el monitor interno

Ubicación: [permisos del monitor](<C:/Ingenieria de software/panaderia_amada/app/monitor/routes.py:179>), [API de lectura](<C:/Ingenieria de software/panaderia_amada/app/monitor/routes.py:192>) y [API de escritura](<C:/Ingenieria de software/panaderia_amada/app/monitor/routes.py:208>).

Las tres rutas incluyen el rol `Invitado`. La entrada pública `/cliente/invitado` autentica ese perfil; la API devuelve los encargos activos con nombres, teléfonos y detalles, y permite cambiar cualquier estado por código sin comprobar propiedad. Un visitante puede obtener esos códigos desde la misma API. Marcar como entregado también puede disparar el cobro automático.

**Evidencia:** cliente Flask con invitado sintético, inicio por la ruta pública y CSRF real: lectura 200 y actualización 200 con commit sobre conexión simulada. No se escribió un pedido real. **Corrección:** excluir invitados de las rutas internas, mantener el seguimiento público limitado a su documento y probar una matriz de roles para cada operación.

### 02 · P1 · El registro anónimo permite publicar HTML activo y sobrescribir archivos

Ubicación: [subida de foto](<C:/Ingenieria de software/panaderia_amada/app/auth/routes.py:213>).

`secure_filename` limpia el nombre pero no valida el contenido ni exige una imagen. Una foto llamada `audit-proof.html` se guarda en `static/uploads/perfiles` y se sirve públicamente como `text/html`. Al abrirla, su JavaScript comparte origen con la aplicación y puede operar con la sesión de quien la visite. Otra alta con el mismo nombre reemplaza el archivo.

**Evidencia:** POST anónimo con token CSRF obtenido por GET; respuesta 302 y descarga 200 con MIME HTML. La prueba usó un directorio estático aislado y demostró también la colisión de nombres. **Corrección:** validar y redecodificar imágenes, generar nombres aleatorios y servir archivos con un tipo seguro; considerar un origen separado para contenido aportado por usuarios.

### 03 · P1 · Un teléfono sin verificar permite acceder a cotizaciones ajenas

Ubicación: [teléfono guardado en sesión](<C:/Ingenieria de software/panaderia_amada/app/pos/routes.py:364>), [consulta](<C:/Ingenieria de software/panaderia_amada/app/pos/routes.py:424>), [aceptación](<C:/Ingenieria de software/panaderia_amada/app/pos/routes.py:535>) y [rechazo](<C:/Ingenieria de software/panaderia_amada/app/pos/routes.py:582>).

Crear una solicitud con el teléfono de otra persona guarda ese número en la sesión. Luego se utiliza como autorización alternativa para listar, aceptar o rechazar cotizaciones, incluso con otro `ClienteID`.

**Evidencia:** invitado sintético 666 usa el teléfono de la cotización 42, propiedad del cliente 88: creación, lectura, aceptación y rechazo responden 200. **Corrección:** autorizar por cliente autenticado o token de propiedad opaco por sesión; eliminar el teléfono declarado como credencial y reutilizar una sola política en todos los endpoints.

### 04 · P1 · El monitor interpreta notas y especificaciones como HTML

Ubicación: [especificaciones](<C:/Ingenieria de software/panaderia_amada/templates/monitor.html:261>), [notas](<C:/Ingenieria de software/panaderia_amada/templates/monitor.html:271>) y [asignación innerHTML](<C:/Ingenieria de software/panaderia_amada/templates/monitor.html:327>).

Se interpolan textos del encargo sin escapar. El flujo de cotización recoge especificaciones del cliente; POS las conserva y el registro del encargo las guarda. La serialización inicial con `tojson` es segura, pero el renderizado posterior vuelve a convertir el texto en HTML. También deben tratarse los nombres y atributos de imagen/teléfono.

**Evidencia:** en el monitor real de QA se llamó `createCard` con una especificación sintética que contenía un evento de imagen; Edge ejecutó el evento. El payload sólo existió en memoria del navegador, sin guardarlo en BD. Esto demuestra el fallo del renderizador; no se realizó un ataque persistente completo contra datos reales. **Corrección:** construir nodos y usar `textContent`; validar protocolos y asignar atributos mediante APIs DOM. Si se necesita HTML, usar una política de saneamiento explícita.

### 05 · P1 · Una entrega puede confirmar el cobro aunque falle su contabilidad

Ubicación: [excepción contable absorbida](<C:/Ingenieria de software/panaderia_amada/app/monitor/routes.py:274>) y [commit posterior](<C:/Ingenieria de software/panaderia_amada/app/monitor/routes.py:285>).

La ruta actualiza el encargo e inserta el pago pendiente. Si `contabilizar_cobro_encargo` falla, sólo registra una advertencia y confirma la transacción. Un período cerrado o una cuenta faltante puede dejar entrega y pago sin asiento, desalineando los saldos y DGI.

**Evidencia:** servicio contable simulado que lanza excepción: pago insertado, commit verdadero, sin rollback y HTTP 200. **Corrección:** hacer obligatorios pago y asiento en la misma transacción; ante error, rollback de toda la entrega y respuesta recuperable. Separar expresamente una operación de entrega de una confirmación de cobro.

## Hallazgos de prioridad media

### 06 · P2 · La comprobación SMS no garantiza posesión del teléfono

Ubicación: [registro](<C:/Ingenieria de software/panaderia_amada/app/auth/routes.py:196>) y [OTP en sesión](<C:/Ingenieria de software/panaderia_amada/app/auth/routes.py:268>).

Hay dos vías independientes: el POST final de registro no exige un desafío verificado y el OTP se guarda en una cookie de sesión firmada que el navegador puede leer. La firma impide modificarla, pero no oculta su contenido. Se reprodujo tanto el registro sin SMS como la extracción del código sin conocer la clave, usando proveedor SMS simulado y sin `dev_codigo` en la respuesta.

**Corrección:** guardar el desafío en servidor, dejar sólo un identificador opaco en la cookie y exigir verificación vigente vinculada al teléfono normalizado en el POST final. Consumir el desafío y limitar intentos. Arreglar sólo una de las dos vías deja la otra abierta.

### 07 · P2 · TOTP obligatorio bloquea cuentas sin enrolar o recién restablecidas

Ubicación: [login](<C:/Ingenieria de software/panaderia_amada/app/auth/routes.py:57>), [paso TOTP](<C:/Ingenieria de software/panaderia_amada/app/auth/routes.py:87>) y [reset](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_users.py:234>).

Con la política obligatoria y secreto vacío, una contraseña correcta lleva a `/login/totp`, que devuelve a `/login`. La configuración requiere sesión completa, por lo que el usuario no puede salir del circuito. El reset borra el secreto y provoca el mismo caso.

**Evidencia:** ciclo reproducido con usuario sintético. **Corrección:** sesión parcial limitada al enrolamiento, con autenticación completa sólo después de confirmar el segundo factor; probar también el reset.

### 08 · P2 · El kiosco cierra una jornada al reconocer de nuevo a la misma persona

Ubicación: [entrada/salida](<C:/Ingenieria de software/panaderia_amada/app/kiosco/routes.py:144>) y [bucle de cámara](<C:/Ingenieria de software/panaderia_amada/templates/kiosco.html:223>).

Dos frames iguales consecutivos registran primero entrada y luego salida. La pausa visual de seis segundos no protege el backend: quien permanezca frente a la cámara puede cerrar su jornada al llegar.

**Evidencia:** dos POST con reconocimiento simulado del mismo empleado generan entrada/salida con la misma hora. **Corrección:** idempotencia por empleado y operación, ventana temporal en servidor y una intención explícita para registrar salida.

### 09 · P2 · Asistencia y licencia en la misma fecha reducen dos veces las ausencias

Ubicación: [cálculo de ausencias](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_hr.py:438>).

Se resta por separado el número de fechas con asistencia y el de fechas justificadas; no se calcula su unión. Las marcas tampoco se filtran igual que los días esperados. Julio de 2026, con 27 días no domingo y una sola fecha con marca y licencia, devuelve 25 ausencias en lugar de 26.

**Corrección:** trabajar con conjuntos de fechas laborables dentro del período y del empleo: esperadas menos unión de asistidas y justificadas. Añadir pruebas de solapamiento y domingos. El hallazgo es de aritmética del sistema; no es un dictamen sobre normativa laboral.

### 10 · P2 · La liquidación ignora vacaciones ya consumidas

Ubicación: [API](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_hr.py:683>) y [reporte duplicado](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_hr.py:811>).

`dias_vacaciones_pendientes` recibe todas las vacaciones devengadas sin descontar las disfrutadas/pagadas. El sistema dispone de licencias de vacaciones, pero no las consulta. El escenario simulado de un año trabajado y 30 días ya consumidos vuelve a calcular 30 días pendientes.

**Corrección:** consolidar un saldo de vacaciones y compartir un cálculo puro entre API y reporte. Contrastar aparte las reglas laborales aplicables antes de usar importes reales.

### 11 · P2 · El arqueo permite alterar el tipo de cambio desde el cliente

Ubicación: [valor recibido](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_pos.py:114>) y [fallback](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_pos.py:148>).

Se acepta cualquier tipo de cambio positivo enviado; la configuración del servidor sólo se usa si no es positivo. En la reproducción, USD 50 con tasa oficial configurada 36.6243 equivalen a C$1,831.21, pero una tasa enviada 73.2486 cuadra artificialmente C$3,662.43 y evita justificar una diferencia.

**Corrección:** usar la tasa autorizada en servidor, persistir su instantánea y restringir cualquier excepción a una operación autorizada y auditada.

### 12 · P2 · Se pueden registrar mermas negativas

Ubicación: [validación e inserción](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_pos.py:378>).

La comprobación de valor presente y conversión a entero acepta `-100`. La ruta devuelve 200 y commit; la cantidad negativa contamina las métricas de desperdicio. El esquema QA consultado no añade una restricción que lo evite.

**Corrección:** reutilizar `positive_int` y añadir `CHECK (Cantidad > 0)` mediante migración que primero detecte datos históricos incompatibles.

### 13 · P2 · Un egreso y su asiento pueden quedar en meses diferentes

Ubicación: [inserción del egreso](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_accounting.py:114>) y [fecha contable](<C:/Ingenieria de software/panaderia_amada/app/services/contabilidad_service.py:628>).

EgresosPrivados omite `Fecha` y usa el default SQL `GETDATE()`; el asiento utiliza `business_now()` de Nicaragua. Con SQL en UTC, las últimas horas del mes pueden producir egreso en el siguiente mes y asiento en el anterior. Se confirmó la omisión mediante mock y el default mediante metadatos QA; no se afirma una operación real afectada.

**Corrección:** tomar una sola fecha de negocio, insertarla explícitamente y transmitirla al servicio contable. Probar el cambio de mes con relojes distintos.

### 14 · P2 · DGI acepta estructuras contables inválidas si sus sumas cuadran

Ubicación: [validación del motor](<C:/Ingenieria de software/panaderia_amada/app/services/dgi_engine.py:240>).

Una línea con Debe=Haber=10 o dos líneas cero/cero producen `datos_consistentes=True` y cero bloqueantes en snapshots sintéticos. El servicio normal de creación contable sí rechaza esas estructuras. El diagnóstico puede dar conformidad a datos históricos/importados inválidos. En QA no se observaron actualmente esas líneas.

**Corrección:** compartir las invariantes de partida doble: mínimo dos líneas, importe total positivo y un único lado positivo por línea, además de igualdad de sumas y no negativos. No confundir esta brecha con el perfil fiscal pendiente.

### 15 · P2 · El mayor pierde el saldo anterior en meses sin fila de período

Ubicación: [consulta condicionada](<C:/Ingenieria de software/panaderia_amada/app/admin/routes_accounting.py:549>).

Si el mes no tiene registro en PeriodosContables, la ruta no llama al servicio y devuelve movimientos vacíos, aunque la cuenta conserve saldo anterior. La balanza puede mostrar ese saldo mientras el mayor queda vacío.

**Evidencia:** período inexistente simulado y servicio con saldo anterior 100: el servicio nunca se invoca. **Corrección:** consultar el mayor por límites de fecha del mes, exista o no su fila de período; no crear períodos desde GET.

### 16 · P2 · Una prueba del monitor puede modificar la BD habitual

Ubicación: [factory de pruebas](<C:/Ingenieria de software/panaderia_amada/tests/test_monitor.py:8>) y [cambios de estado](<C:/Ingenieria de software/panaderia_amada/tests/test_monitor.py:68>).

La fixture llama `create_app()` sin usar `TEST_DB_CONNECTION_STRING`. La prueba toma el primer encargo activo y lo cambia a En Proceso, Listo y finalmente Pendiente, sin conservar/restaurar necesariamente su estado original. Puede ejecutar escrituras contra la conexión habitual y aprobar sin ejercitar nada si no hay encargos.

**Incidencia de esta revisión:** la primera ejecución global aprobó 141 pruebas, pero aún no tenía el bloqueo de conexiones fuera de QA. Después se comprobó, interceptando la conexión sin abrirla, que esta fixture ignoraba la variable QA. Por ello esa primera ejecución pudo consultar y modificar la BD configurada. No se ha confirmado si había un encargo activo ni si produjo cambios; no se intentó revertir datos a ciegas.

La repetición usó Config forzada a QA en memoria y un guard en `pyodbc.connect`: **141 aprobadas, 184 conexiones QA y 0 fuera de QA**. **Corrección pendiente en producto/tests:** configuración de prueba común con verificación obligatoria de DB_NAME, datos propios por caso y rollback/limpieza, eliminando IDs de usuarios y pedidos existentes como fixtures.

### 17 · P2 · La imagen Docker puede incluir secretos y datos locales

Ubicación: [COPY general](<C:/Ingenieria de software/panaderia_amada/Dockerfile:32>).

Existe `.env` en el checkout y no existe `.dockerignore` ni archivo equivalente junto al Dockerfile. Construir con este directorio como contexto copia también archivos locales no excluidos, aunque Git los ignore. Puede incorporar credenciales, scratch, adjuntos y bases locales. Es una deficiencia del empaquetado; no se afirma que una imagen ya publicada contenga esos archivos.

**Corrección:** contexto explícito y `.dockerignore` que excluya secretos, `.git`, pruebas temporales, respaldos y datos de usuarios; inyectar secretos en ejecución. No se construyó ni subió una imagen durante la auditoría. El comportamiento se contrastó con la [documentación oficial de Docker](https://docs.docker.com/build/concepts/context/#dockerignore-files).

### 18 · P2 · Las dependencias de despliegue difieren de las verificadas y fijan Gunicorn vulnerable

Ubicación: [requirements](<C:/Ingenieria de software/panaderia_amada/requirements.txt:1>) y [Gunicorn fijado](<C:/Ingenieria de software/panaderia_amada/requirements.txt:13>).

El manifiesto fija Flask 3.0.0, Flask-WTF 1.2.1 y Gunicorn 21.2.0; el entorno revisado usa Flask 3.1.3 y Flask-WTF 1.3.0, y no tiene Gunicorn instalado en Windows. Pillow instalado 12.2.0 tampoco satisface el mínimo 12.3.0 declarado. `pip check` aprueba las dependencias entre paquetes instalados, pero no comprueba este manifiesto contra el entorno.

Gunicorn 21.2.0 queda antes de las correcciones de request smuggling de la versión 22, documentadas por el [proyecto](https://gunicorn.org/news/#2200-2024-04-17). La exposición concreta depende del servidor/proxy; no se intentó explotarlo. El aviso de [Flask sobre Vary: Cookie](https://github.com/pallets/flask/security/advisories/GHSA-68rp-wp8r-4726) también afecta al pin antiguo bajo condiciones específicas; la aplicación aplica `no-store` a respuestas autenticadas, por lo que no se declara una filtración demostrada por esa vía.

**Corrección:** resolver versiones mantenidas y compatibles, fijar un entorno reproducible y ejecutar la suite y el arranque sobre las mismas dependencias y plataforma de despliegue. No basta con actualizar el número mínimo de Gunicorn sin revisar avisos posteriores.

## Hallazgo menor

### 19 · P3 · El manual administrativo rechaza al administrador legítimo

Ubicación: [rol en minúscula](<C:/Ingenieria de software/panaderia_amada/app/admin/manual_admi.py:15>).

Exige `admin`, mientras los roles usados por el sistema son `Admin` y `SuperAdmin`. Un administrador sintético recibe redirección al hub. **Corrección:** reutilizar los nombres canónicos y probar ambos roles.

## Resultado de los cinco ejes

| Eje | Evaluación y acción concreta |
| --- | --- |
| Funcionamiento | Hay escenarios reproducibles de cobros sin asiento, asistencia incorrecta, liquidación y reportes incompletos. Priorizar invariantes y errores transaccionales antes de nuevas funciones. |
| Seguridad | Corregir permisos de invitado, propiedad de cotizaciones y ambos puntos de ejecución HTML. Mantener CSRF; los casos de invitado y alta se reprodujeron con CSRF real. |
| Arquitectura | Unificar autorización de cotizaciones, cálculo de liquidación, validación contable y configuración de tests. La ruta debe orquestar servicios transaccionales, sin absorber fallos financieros. |
| Legibilidad | RRHH y POS concentran responsabilidades y duplican cálculos. Extraer funciones por operación de negocio con entradas/salidas claras; evitar mover las mismas ramas a archivos nuevos sin simplificarlas. La nueva organización CSS sí tiene paquetes y orden verificables. |
| Rendimiento | No hay medición de carga que permita afirmar capacidad productiva. El monitor carga todos los activos; el cálculo de ventas consulta productos/ingredientes por línea y biometría ejecuta inferencia síncrona. Medir volúmenes, consultas y latencias antes de decidir paginación, consultas por lotes o workers. No se declara un fallo de rendimiento probado. |

## Verificación y cobertura

- **Suite global protegida:** 141 passed, 1 warning, 53.52 s. Guard de conexión: 184 QA, 0 externas. El warning es el uso de `datetime.utcnow()` por Flask-Login, no un fallo de cálculo demostrado.
- **Navegador Edge contra servidor QA separado en 5073:** cuatro scripts aprobados, sin errores JavaScript detectados en sus recorridos. Menú, foco, Escape, confirmaciones, formularios cancelados, descarga repetida, catálogo/filtros/carrito sin enviar pedido, temas, movimiento normal/reducido y carga de 18 páginas. Vistas de 320, 390, 768 y 1440 px según el escenario; no todas las páginas tienen pruebas exhaustivas en todos los tamaños.
- **CSS:** `python scripts/build_css.py --check`: 43 paquetes verificados.
- **Dependencias instaladas:** `python -m pip check`: sin dependencias internas rotas; no equivale a instalar requirements ni certificar un contenedor.
- **Pruebas adicionales aisladas:** autenticación/uploads 5 aprobadas; DGI/fiscal/hora 63 aprobadas; fiscal 30 aprobadas. Son subconjuntos solapados con la suite, no se suman como cobertura distinta.
- **Mutación DGI en memoria:** invertir la comparación de Debe/Haber provoca 5 fallos y 23 aprobadas; la suite detecta esa regresión.
- **Mutación fiscal en copia aislada:** permitir estados Pendiente/Rechazada en la consulta mantiene las 30 pruebas verdes. Falta un caso que ejercite la condición real de estados facturables; el mock actual no valida esa parte de SQL. No se calculó un porcentaje global de mutación.
- **Reproducciones adversarias:** scripts con SQL bloqueado/mocks, más prueba del renderizador en navegador. No son explotaciones de extremo a extremo contra la BD habitual.

Revisión distribuida por autenticación/usuarios/RRHH/kiosco; ventas/caja/inventario/producción; DGI/fiscal/contabilidad; e integración, interfaz, configuración y pruebas. Se contrastaron rutas, servicios, modelos, plantillas, esquema/migraciones pertinentes y sus tests. No se certifica ausencia de problemas en cada línea ni se valida normativa fiscal/laboral.

La configuración fiscal pendiente, el diagnóstico interno y el bloqueo de presentación oficial DGI son el alcance autorizado y **no se consideran errores**. No se confirmó un defecto adicional de idempotencia u obsolescencia de revisiones DGI en los casos revisados. Una consulta QA observó un asiento histórico cuya fecha y período difieren; el creador actual ya valida esa relación, por lo que queda como dato para reconciliar, sin atribuirlo a la implementación actual ni repararlo.

No se hicieron envíos SMS reales, reconocimiento facial con personas, pruebas de carga, reconstrucción Docker, migraciones productivas ni validación de infraestructura pública. Los cambios locales previos se conservaron. Las correcciones propuestas quedan pendientes; el estado aprobado de las pruebas existentes no cierra estos hallazgos.

## Evidencia local y orden de corrección

La evidencia técnica está en [scratch de auditoría](<C:/Ingenieria de software/panaderia_amada/scratch/audit_20261017/>). Incluye `pytest-guarded.xml`, `guarded-suite.json`, `test-isolation.json`, `monitor-browser.json`, los resultados/capturas de `browser/` y las reproducciones por dominio. Scratch está ignorado por Git; conservarlo de forma privada si se necesita trazabilidad futura, sin publicarlo indiscriminadamente.

1. Aislar definitivamente las pruebas y cerrar permisos, propiedad y HTML activo (01–04,16).
2. Hacer atómicos entrega/cobro/asiento; corregir SMS/TOTP, tipo de cambio y validaciones (05–07,11–12).
3. Corregir asistencia, saldo de vacaciones, fechas de egresos y reportes contables/DGI con pruebas de regresión (08–10,13–15).
4. Construir y verificar un despliegue reproducible sin secretos; cerrar el manual (17–19).

Cada corrección debe aportar un caso que falle con el código auditado y apruebe tras el cambio, usando exclusivamente datos sintéticos y una BD identificada como QA.
