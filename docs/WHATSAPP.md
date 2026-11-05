# Atención WhatsApp

Implementación opcional para Flask y SQL Server. El servidor web nunca inicia Neonize.
Codex implementó el canal sobre la rama existente, preservando los cambios de autenticación
que ya estaban presentes. El transporte no oficial mantiene el riesgo operativo descrito
en la evaluación previa; mostrar presencia de escritura no evita restricciones.

## Instalación en un entorno de prueba

1. Instalar las dependencias de aplicación desde `requirements.lock` y después
   `python -m pip install -r requirements-whatsapp.txt` en el entorno del worker.
   Neonize está fijado en 0.10.0. Requiere su biblioteca nativa; no es Python puro.
   Para funciones multimedia ampliadas, Neonize recomienda FFmpeg. El bot solo recibe
   texto y JPEG/PNG/WebP; no interpreta fotos, audio, documentos ni videos.
2. Respaldar la base y aplicar la migración aditiva primero en una QA aislada:
   `python scripts/migrate_whatsapp.py --connection-env TEST_DB_CONNECTION_STRING`.
   El script carga `.env` cuando está disponible. La variable debe apuntar a
   una base cuyo nombre empiece por `PanaderiaQA_`. No se ejecutó durante el desarrollo.
   Para otro destino, el operador debe seleccionar explícitamente la variable y
   `--allow-production`, después de comprobar QA. No ejecutar `esquema.sql`.
3. El login de aplicación debe poder suplantar al nuevo usuario contenido
   `usr_bd_whatsapp`, además de los usuarios SQL que ya necesita el sistema.
   La migración no concede permisos a un login externo desconocido. El worker usa
   procedimientos acotados y el usuario público existente para catálogo/seguimiento;
   no dispone de herramientas de cobro, caja, facturación, RR. HH. ni DGI.
4. Configurar `WHATSAPP_ENABLED=1` tanto en Flask como en el worker solamente después
   de aplicar y verificar la migración. Por defecto no se consulta ninguna tabla nueva
   al operar el POS/KDS. La bandera habilita la integración; el interruptor del panel
   controla la atención y los envíos y empieza apagado.
5. Configurar `GEMINI_API_KEY`. Opcional: `WHATSAPP_MODEL` (predeterminado
   `gemini-3.8-flash`) y `WHATSAPP_SESSION_PATH` (predeterminado
   `instance/whatsapp_session.sqlite3`). La implementación incluye Gemini por REST;
   otros proveedores requieren un adaptador con el contrato `complete(messages, schemas)`.
   Verificar disponibilidad, cuota y tratamiento de datos con el proveedor elegido.
6. Ejecutar `python scripts/run_whatsapp.py` en un proceso distinto del servidor web.
   Usar un servicio/supervisor del sistema operativo con reinicio ante fallo y un solo
   worker por cuenta/base. El bloqueo de sesión SQL rechaza un segundo worker.
7. Ingresar a `/admin/whatsapp` como Admin/SuperAdmin, actualizar para obtener el QR
   y vincular una cuenta de prueba desde Dispositivos vinculados. Activar el interruptor
   y probar primero con números controlados. No se vinculó una cuenta real al desarrollar.

## Qué puede hacer

- Consultar catálogo activo sin productos ficticios, precios y descuentos actuales.
- Usar las recomendaciones públicas existentes, sin acceder al historial personal.
- Registrar cotizaciones del propio chat con fecha/hora de Nicaragua y anticipación
  mínima de 24 horas; máximo tres solicitudes abiertas por sesión.
- Listar y aceptar/rechazar cotizaciones creadas por ese chat. Antes de modificar,
  muestra los detalles y exige un mensaje literal `CONFIRMAR`, válido 15 minutos.
  Aceptar no registra pagos, no emite factura ni envía un pedido a cocina.
- Rastrear con el código privado del pedido, devolviendo estado, entrega, total y saldo.
- Recibir imágenes de referencia (5 MB, 16 megapíxeles como máximo), verificarlas y
  recodificarlas sin metadatos. Reutiliza la carpeta pública de referencias existente;
  no enviar imágenes sensibles. Worker y Flask necesitan compartir ese almacenamiento.
- `HUMANO` solicita atención personal. El panel permite tomar control, responder y
  reactivar IA. Al reactivar se archivan mensajes acumulados para evitar respuestas antiguas.
- `AVISOS SI` autoriza notificaciones; `AVISOS NO` las desactiva. La autorización es
  explícita y queda registrada en el inbox. Cotizaciones solo avisan a su sesión privada;
  los avisos de cocina usan el teléfono de contacto y requieren consentimiento previo.
  Esos avisos no conceden acceso al historial de cotizaciones.

## Operación y recuperación

Inbox, outbox y resultados de herramientas son persistentes. Se deduplican mensajes
por sesión/MessageID y operaciones por clave. El worker procesa una conversación a la vez,
limita cada remitente a seis mensajes por minuto y cada respuesta a cuatro herramientas.
La entrega global tiene un intervalo mínimo de dos segundos. Los límites son medidas
de capacidad; no garantizan evitar restricciones del canal.

POS y cocina insertan avisos en su propia transacción: si hay rollback no queda el aviso.
La dependencia de mensajería no participa de la transacción mediante llamadas de red.
Durante el envío se bloquea únicamente el estado del canal para impedir una carrera
con la toma de control humana. El panel puede esperar mientras termina ese envío.
La sesión SQL que mantiene el singleton se comprueba en cada iteración; su pérdida
detiene el worker. Supervisar Heartbeat (caduca a los 30 segundos) y eventos de desconexión.

Los envíos fallidos esperan 15, 30, 60 y 120 segundos y quedan `Fallido` al quinto intento;
el historial del panel muestra el estado. El inbox marca `Fallido` después de tres intentos.
El operador revisa la causa antes de reenviar. La entrega externa es al menos una vez:
si WhatsApp acepta un mensaje y SQL falla antes de confirmarlo puede haber un duplicado.
No se promete entrega exactamente una vez. La creación/aceptación usa auditoría transaccional
para impedir repetir efectos de la misma confirmación.

Proteger la SQLite de sesión con permisos del usuario de servicio y almacenamiento
persistente; no publicarla, copiarla al repositorio ni compartir su QR. `instance/` está
ignorado. Mantener TLS y CSRF del panel. Al desactivar `WHATSAPP_ENABLED`, los hooks dejan
de consultar el canal. El interruptor SQL apaga respuestas y envíos, pero conserva historial.

Antes de operación real: verificar la migración dos veces en SQL Server QA, permisos
efectivos, rechazo de una cotización ajena, reconexión y persistencia tras reinicio,
duplicados, toma humana durante inferencia, rechazo de archivos inválidos y rollback
del POS/KDS sin aviso. Esas pruebas requieren SQL Server y una cuenta controlada.

Definir con la panadería conservación y depuración del historial, imágenes y resultados
del proveedor antes de habilitar clientes reales. El desarrollo no instala un borrado
automático de registros comerciales.

## Verificación local del 4 de noviembre de 2026

Suite completa: **441 aprobadas y 104 omitidas**, con destino SQL de prueba vacío y
carga de `.env` deshabilitada. Las pruebas nuevas verifican políticas, imágenes,
autorización del panel, ejecución acotada del agente, pausa humana y persistencia con
un adaptador transaccional SQLite. Este adaptador no certifica permisos ni semántica
de bloqueo de SQL Server. Los casos SQL omitidos no se presentan como aprobados.

Compilación Python, manifiesto de 46 paquetes CSS y diff verificados. Vista del panel
comprobada con datos sintéticos en Chrome a 390 y 1440 píxeles, incluida carga efectiva
del CSS y ausencia de desbordamiento. Neonize instalado e importado en un entorno
aislado con Python 3.14.4; `pip check` sin incompatibilidades en ese entorno opcional.
No se inició una conexión real a WhatsApp ni se utilizó una clave de IA.

## Modelos Gemini y respaldo automático

La actualización posterior autorizada el 4 de noviembre consultó el catálogo con la
clave del usuario: Google devolvió HTTP 200 y 60 modelos. La clave se guardó en `.env`
ignorado por Git y el catálogo sin credenciales en `instance/gemini-models.json`.
No se publica ninguna clave en código, documentos ni registros.

Para atención con herramientas se seleccionó **Gemini 3.8 Flash** como principal por
su equilibrio de capacidades de agente y velocidad. **Gemini 4 Argon** es el modelo
insignia de razonamiento, orientado a tareas más exigentes; no se midió un benchmark
comparativo del negocio. Fuentes: [3.8 Flash](https://aistudio.google.com/docs/models/gemini-3.8-flash),
[4 Argon](https://aistudio.google.com/docs/models/gemini-4-argon).

`WHATSAPP_MODELS` configura el orden completo separado por comas; tiene prioridad
sobre `WHATSAPP_MODEL`. Si no se define, el adaptador usa la lista de 14 modelos
de texto/herramientas de `app/whatsapp/gemini.py`. Si solo se define `WHATSAPP_MODEL`,
se coloca primero y se conservan los respaldos. No se usan modelos de audio, música,
imágenes, embeddings ni aliases `latest`, que pueden apuntar a la misma cuota.
No se habilitan automáticamente modelos nuevos sin comprobar su compatibilidad.

Ante HTTP 429, 404/410, 408, 500/502/503/504 o errores temporales de conexión,
se enfría ese modelo y se intenta otro. Se respetan Retry-After y RetryInfo de Google.
Se hacen como máximo tres intentos de inferencia por llamada, con presupuesto de
60 segundos y sin bloquear el worker durmiendo entre reintentos. Las siguientes
consultas saltan modelos en enfriamiento y vuelven a priorizarlos cuando vence.
Los enfriamientos son locales al worker y se reinician al reiniciarlo.

No se rota ante 400/401/403, peticiones incorrectas ni respuestas bloqueadas/vacías.
Las herramientas comerciales se ejecutan únicamente después de una inferencia
exitosa, conservando claves de idempotencia. Se mantienen las firmas y los IDs de
llamadas para el mismo modelo; al cambiar se pasan los resultados previos como datos,
sin reutilizar firmas del otro modelo. Se permiten hasta cuatro herramientas en total,
incluidas llamadas paralelas de una misma respuesta.

Las cuotas se aplican al proyecto y varían por modelo: cambiar no resuelve límites
compartidos, de gasto o de facturación. Ver [límites oficiales](https://aistudio.google.com/docs/rate-limits).
La prueba real del adaptador recibió HTTP 503 de 3.8 Flash por alta demanda y
continuó automáticamente con **3.5 Flash-Lite**, que respondió correctamente.
Se priorizó ese respaldo comprobado en la configuración local y en el orden por defecto.
El catálogo validado no equivale a cuota garantizada para cada uno de los 14 candidatos.
Las pruebas automáticas simulan cuotas y errores sin consumir la API real.

Verificación de esta actualización: **456 pruebas aprobadas, 104 omitidas**.
Se comprobó además que `.env` y el catálogo local están ignorados por Git.

## Entrega de producción del 4 de noviembre de 2026

Se corrigió el cierre del transporte para cancelar el contexto nativo con `stop()`.
La inferencia se ejecuta en un único hilo con contexto Flask propio, mientras el hilo
principal mantiene la señal de salud y despacha respuestas humanas y notificaciones.
Cada operación SQL abre su propia conexión; no se comparten cursores entre hilos.
El singleton se conserva hasta terminar la operación en curso y se libera incluso
si falla la actualización final de estado. Las dos regresiones tienen pruebas en
`tests/test_whatsapp_worker.py`.

El workflow de `main` ejecuta la suite sin SQL operativo y verifica los estilos antes
de desplegar. `scripts/build_deployment.py` genera un ZIP explícito de ejecución:
aplicación, vistas, estáticos, configuración, dependencias y entrada del worker.
Excluye `.env`, credenciales, sesiones, archivos subidos, scratch y entornos locales.
Las dependencias de Neonize se instalan también en los destinos de producción.

El despliegue web sigue iniciando Gunicorn. El worker debe ejecutarse por separado
con `python scripts/run_whatsapp.py`, bajo el supervisor del destino y con almacenamiento
persistente. Subir a `main` no equivale a vincular el teléfono ni activar el interruptor
del bot. No se insertan claves locales en Git ni en el ZIP; deben configurarse en Azure.
