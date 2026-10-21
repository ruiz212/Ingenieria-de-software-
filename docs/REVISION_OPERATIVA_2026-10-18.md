# Revisión operativa a partir de las capturas — 18 de octubre de 2026

El cierre anterior verificaba los 19 hallazgos enumerados en la auditoría, pero no justificaba afirmar que toda la aplicación estaba reparada. Las capturas del usuario motivaron esta nueva revisión con tres agentes: navegación, monitor de cocina y coherencia del resumen. Se conservaron los cambios anteriores del proyecto.

## Hallazgos y correcciones

| Hallazgo comprobado | Corrección |
| --- | --- |
| El resumen contaba encargos según la fecha de la factura de hoy y mostraba 100% cuando no había ninguno; cocina consultaba pendientes de cualquier día. | «Encargos por entregar» cuenta el mismo conjunto operativo global que cocina. Incluye listos y atrasados y declara «Todos los días». Las ventas conservan su alcance diario. |
| Respuestas HTTP de error dejaban el monitor en verde; un JSON sin lista podía borrar las tarjetas. | Estados de actualización y error explícitos, rechazo de sesión vencida/redirección, JSON y estructuras inválidas; se conserva la última lista confirmada. Peticiones limitadas a 10 segundos. |
| Un GET podía sustituir/reordenar la lista mientras un PUT usaba un índice anterior para revertir o retirar un pedido. | Estado confirmado por el servidor, identidad por código, bloqueo de duplicados por pedido y descarte de GET anterior a un cambio. Sin movimiento optimista que anuncie éxito antes de confirmación. |
| La actualización periódica destruía el foco. | Conserva posición de lectura y foco por código/acción; un cambio confirmado mantiene continuidad hacia la tarjeta movida. No debe robar el foco si el usuario eligió otro control durante la espera. |
| Con texto al 200% y poca altura, el área desplazable era menor que el propio botón. | Altura mínima del monitor proporcional al texto, tarjetas sin compresión, columnas enfocables, indicación de desplazamiento y ajuste de palabras largas. Se permite desplazamiento exterior cuando hace falta. |
| La marca de la barra lateral enviaba a perfiles operativos al resumen restringido a administradores. | Usa el hub existente, que elige un destino permitido según el rol. |

El renderizador conserva nodos y `textContent`, sin interpolar datos de clientes como HTML ejecutable. El JavaScript de tarjetas lleva una versión nueva en su URL y el CSS fue regenerado.

## Aparente ausencia de navegación: sospecha no confirmada

Las capturas muestran contenido sin el espacio lateral ni el botón móvil. No se reprodujo esa ausencia con el HTML y los estilos actuales en el servidor QA ni en fixtures con distintos roles. Una comparación adicional mostró que una pantalla de 1920 píxeles con escala 1,25 y barra lateral de 330 píxeles deja un área principal de 1590 píxeles, prácticamente la medida de las capturas del usuario. Recortar sólo esa área produce el mismo encuadre aunque la navegación esté visible. Esto no demuestra que el usuario recortara la imagen; tampoco permite concluir, sólo a partir de ella, que el menú estuviera oculto. No se comprobó una causa de caché, zoom o breakpoint.

Los archivos públicos CSS del servidor habitual y de QA coincidían con el código actual. Las pruebas nuevas comprueban límites de pantalla, intersección para recibir clics, `inert`, navegación real, redimensionado, varios anchos y densidades, ambos temas y funcionamiento sin JavaScript. `isVisible()` por sí solo no demuestra que un control pueda usarse.

No se pudo inspeccionar el DOM de la sesión abierta del usuario: la herramienta de navegador falló al inicializar, también después de reiniciarla. No se extrajeron cookies ni se fabricaron sesiones para acceder a la base habitual. **La ausencia de navegación sigue como sospecha no confirmada; no se presenta como un fallo diagnosticado o reparado.**

## Evidencia y límites

- Suite general: **264 pruebas aprobadas**, sin omisiones, con SQL QA explícito; 4 avisos de obsolescencia de Flask-Login. Registro: `scratch/recheck_20261018/pytest.log` y XML adjunto.
- Seis pruebas nuevas de navegación por roles aprobadas; además, la ejecución conjunta de esas seis y las doce de alcance de encargos dio **18 aprobadas**. Las doce del dashboard fallaron antes de su corrección; la marca falló para cuatro roles antes del cambio.
- Comprobación de **18 páginas** y recorridos generales de navegación, confirmaciones, descargas, movimiento normal y reducido aprobados en Edge.
- Comparación de dashboard, API de cocina y tablero aprobada sobre QA sin escrituras de negocio. En esa base el conjunto activo estaba vacío; los casos históricos, no vacíos, fiscales y de fechas se ejercitan con datos sintéticos y consultas reales traducidas a SQLite.
- **43 paquetes CSS** generados y comprobados. Pruebas específicas de cocina y navegación: resultados y capturas en `scratch/recheck_20261018/kds/` y `scratch/recheck_20261018/navigation/`; sus baterías incluyen casos de error y accesibilidad adicionales.
- Navegación: **108 combinaciones** de ancho, densidad y tema aprobadas, más **2 casos sin JavaScript** y **12 fixtures de roles**. Cocina: **20 casos funcionales**, **5 comprobaciones contra HTML hostil** y **8 escenarios visuales** aprobados, incluido texto al 200% con estados y acciones legibles.
- Revisión independiente reprodujo productos nulos, cliente numérico con búsqueda y pérdida de foco durante PUT; se corrigieron y se volvieron a comprobar esos contraejemplos.

Estas pruebas no equivalen a validar exhaustivamente todas las operaciones ni un entorno productivo. Las respuestas de red adversas y los cambios de estado del navegador usan fixtures/interceptores, sin cobrar, entregar pedidos reales, enviar SMS ni escribir asistencias.

## Servidor local

El proceso habitual del puerto 5000 no recargaba Python automáticamente. Durante el reinicio se detectó otro proceso antiguo asociado al mismo puerto: al detener el proceso 39020, el control posterior seguía mostrando el 35388, iniciado el día anterior. Ambos procesos antiguos de `run.py` se retiraron. Se comprobó que el puerto queda atendido por el proceso actualizado 34016, con Python 3.12, y que la petición de comprobación aparece en su propio registro, no sólo que alguna respuesta devuelva 200.

El árbol actual incluye el lanzador del entorno virtual y su intérprete hijo: no son dos servidores distintos. El servidor QA anterior de 5065 se conservó; el temporal de esta revisión, 5074, se detuvo al concluir las pruebas.

Se comprobó `GET /login` → 200 con formulario y que el CSS del monitor servido coincide con el paquete generado. El reinicio carga la consulta corregida del resumen; las páginas ya abiertas necesitan recargarse. La existencia de procesos antiguos confirma un problema de activación del código, pero no demuestra por sí sola la causa del encuadre de las capturas. Para futuros arranques locales, detener la instancia anterior antes de iniciar otra.

No se aplicaron migraciones ni se escribieron datos en la base habitual/Azure. Las migraciones y límites pendientes del cierre anterior siguen documentados en `REPARACIONES_AUDITORIA_2026-10-17.md`. El reinicio local no acredita por sí solo los flujos autenticados contra esa base. No hubo publicación ni commits.

Los directorios `scratch` contienen evidencia privada y acceso de QA; no deben publicarse con el informe.
