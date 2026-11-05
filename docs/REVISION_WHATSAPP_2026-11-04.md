# Revisión de implementación de WhatsApp — 4 de noviembre de 2026

Dictamen: el núcleo y la migración están implementados e instalados, pero no se
certifica todavía una operación completa y continua. Revisión realizada por Codex,
sin aplicar migraciones, modificar datos comerciales, iniciar el worker ni enviar mensajes.
El informe aportado por el usuario se contrastó con archivos y consultas de solo lectura.

Actualización posterior para la entrega autorizada a producción: los hallazgos 1 y 2
se corrigieron y cuentan con pruebas de regresión en `tests/test_whatsapp_worker.py`.
La entrega web incluye el código y las dependencias del worker, sin arrancarlo dentro
de Gunicorn. La vinculación, supervisión y prueba real del canal del hallazgo 3 siguen
siendo pasos operativos independientes. El detalle siguiente conserva la evidencia
del diagnóstico inicial, no afirma que esas dos correcciones sigan pendientes.

## Hallazgos que requieren atención

1. **P1 — El cierre no cancela el proceso nativo.**
   `app/whatsapp/client.py:83` implementa `Transport.stop()` con `disconnect()`.
   En Neonize 0.10.0 instalado, `connect_with_proxy()` mantiene un hilo nativo no daemon
   hasta cancelar su contexto con `stop()`/`Stop`. Desconectar la sesión de red no
   equivale a cancelar ese contexto. El cierre por Ctrl+C o por fallo SQL puede dejar
   al proceso esperando el hilo nativo y dificultar su reinicio por un supervisor.
   Remedio: invocar la cancelación nativa y esperar al conector con un cierre acotado;
   garantizar liberación de la conexión de bloqueo aunque falle la actualización de estado.
   La prueba aislada de revisión confirmó que el método de cancelación nunca se llama.
   No se detuvo una cuenta real para probarlo.

2. **P2 — Una inferencia lenta interrumpe la señal de salud y retrasa los envíos.**
   `app/whatsapp/worker.py:60` actualiza Heartbeat en el mismo bucle que ejecuta
   `process()` en la línea 67. El proveedor permite hasta 60 segundos por llamada y el
   agente puede hacer varias llamadas. `app/whatsapp/routes.py:19` declara caído al
   worker tras 30 segundos. Una prueba con reloj simulado y una inferencia de 60 segundos
   reprodujo un intervalo de Heartbeat de 60 segundos; el panel puede mostrar una caída
   falsa. Mientras tanto, respuestas humanas y avisos también esperan al bucle.
   Remedio: separar señal de salud y despacho de la inferencia, preservando el singleton,
   la serialización por conversación y el aislamiento de conexiones SQL.

3. **P2 — Falta la puesta en marcha verificable del canal.**
   En el equipo inspeccionado no se detectó un proceso `run_whatsapp.py`, ni archivo de
   sesión en la ruta configurada. SQL devuelve `Activo=0`, `Estado=Desconectado`,
   Heartbeat nulo y ningún QR guardado. `WHATSAPP_ENABLED=1` habilita la integración,
   pero no inicia el servicio ni vincula el teléfono. No se encontró configuración de
   supervisor del worker en Docker/workflow; Docker solo inicia Gunicorn y no instala
   `requirements-whatsapp.txt`. Remedio: definir y probar el servicio independiente,
   persistencia, reinicios y vinculación con cuenta controlada antes de activar clientes.
   Esto describe el equipo y archivos inspeccionados, no inventaría otros servidores.

## Evidencia comprobada

- Conexión SQL configurada disponible; se localizaron las cinco tablas, dos índices y
  40 procedimientos esperados. Las definiciones coinciden con el archivo local;
  las únicas dos diferencias detectadas inicialmente eran comentarios de encabezado.
- Matriz de permisos efectivos consultada mediante `HAS_PERMS_BY_NAME` e identidades
  SQL temporales: worker puede crear sesiones y no activar el bot; caja/cocina pueden
  notificar y no activar/crear sesiones; portal no puede ejecutar esas operaciones.
  Worker/caja/cocina no pueden leer directamente sesiones ni actualizar cotizaciones.
  Gerencia/superadmin tienen acceso administrativo. No se ejecutaron operaciones de negocio.
- Importación de Neonize y pyodbc correcta. Clave Gemini presente, modelo principal
  `gemini-3.8-flash`; no se imprimieron claves ni cadenas de conexión.
- Hooks presentes: cotización en `app/pos/routes.py:766` y cocina en
  `app/monitor/routes.py:377`, antes del commit.
- Suite actual: **456 aprobadas, 104 omitidas**, en 88,67 segundos, con conexión QA
  vacía y carga de `.env` deshabilitada para las pruebas. Las omitidas no son aprobadas.
- Pruebas adicionales de auditoría aislada: **dos fallos reproducidos**, correspondientes
  a los hallazgos 1 y 2. Están en scratch, no forman parte de la suite oficial ni fueron
  convertidas en correcciones en esta revisión.
- CSS: 46 paquetes verificados. `git diff --check` sin errores de espacios.

## Alcance frente al plan original

Están presentes siete herramientas, agente Gemini con respaldo, persistencia,
confirmación explícita, propiedad por token del canal, imágenes, panel con control humano
y avisos transaccionales. Las recomendaciones son generales por decisión del diseño
revisado; no se vincula una cuenta histórica por mera coincidencia telefónica.

La propuesta inicial también incluía ingredientes/extras en el catálogo y configuración
de anticipación/cupo. La herramienta actual consulta productos pero no ingredientes;
24 horas y tres cotizaciones están fijados en Python/SQL. Esos puntos no están completos
si se exige reproducir literalmente el plan inicial. El horario comercial tampoco tiene
un filtro implementado. El panel sí conserva el interruptor global.

El manual conserva texto antiguo diciendo que la migración no lee `.env`, aunque
`scripts/migrate_whatsapp.py` ahora sí lo carga; debe actualizarse para evitar confusión.

## Límites de esta revisión

La presencia y coincidencia de objetos no demuestra por sí sola todas las siete pruebas
históricas del informe adjunto. No se repitieron inserciones, rollbacks comerciales ni
la migración dos veces sobre la base operativa. No se encontró una suite SQL específica
de WhatsApp conservada en tests; las pruebas persistentes actuales usan un adaptador
SQLite. Conviene conservar las comprobaciones de permisos, propiedad, confirmaciones,
atomicidad y concurrencia en QA como pruebas reproducibles.

Pendiente: corregir los dos fallos de ciclo de vida/monitorización, ejecutar las pruebas
SQL reproducibles en QA, configurar el supervisor y probar de extremo a extremo QR,
entrada real, herramientas, confirmación, imagen, aviso y transferencia humana.
Hasta entonces la conclusión es «implementado con pendientes de operación», no «100% listo».
