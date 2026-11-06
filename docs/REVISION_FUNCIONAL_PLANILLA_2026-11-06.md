# Planilla y revisión funcional — 6 de noviembre de 2026

## Corrección comprobada

Las rutas de cálculo individual y masivo pasaban los argumentos del IR acumulado
en orden incorrecto: enviaban el IR retenido donde el motor esperaba el mes, y el
mes donde esperaba el IR retenido. Con historial anual podía calcularse un IR
incorrecto, dejar el neto en cero y provocar el rechazo por partida doble.

Se usan ahora los nombres explícitos de los cuatro argumentos. No se cambió la
tabla tributaria, el motor de cálculo, las restricciones del período ni la
transacción. No se recalcularon ni modificaron nóminas anteriores.

Se reprodujo el error con consultas SQL de lectura y escrituras simuladas; el
asiento simulado estaba descuadrado antes de la corrección y equilibrado después.
El diagnóstico no ejecutó INSERT, UPDATE, DELETE, generación ni pago en producción.
La confirmación de la transacción en esa simulación es únicamente una bandera en
memoria, no un commit de nóminas en SQL Server.

Las 12 regresiones nuevas ejercitan ambas rutas con empleados ficticios: retención
previa cero, parcial y superior al impuesto acumulado; comprueban el importe de IR,
partida doble, cierre de conexión, commit al terminar y rollback si falla el asiento.
Antes del arreglo fallaban las seis variantes de generación exitosa; después pasan.

## Matriz de verificación

Suite completa: **496 aprobadas, 168 omitidas**. Los grupos de esta tabla son una
clasificación de los archivos de prueba, no una certificación de cada operación
en el servidor real.

| Área | Aprobadas | Omitidas | Evidencia y límites |
| --- | ---: | ---: | --- |
| RR. HH. y motor de planilla | 50 | 7 | Cálculos, períodos, asistencia y nuevas regresiones HTTP; sin pagos reales. |
| POS, WhatsApp y caja | 106 | 22 | Pruebas de transacciones/avisos y ocho recorridos adicionales en Edge con HTTP sintético; sin enviar mensajes. |
| Contabilidad, fiscal y DGI | 105 | 29 | Motores, compatibilidad de lectura y regresiones; operaciones SQL completas requieren QA. |
| Seguridad y acceso SQL | 77 | 71 | Autenticación, sesiones, permisos simulados y bloqueo de conexiones inseguras. |
| Interfaz y rendimiento | 35 | 0 | Recursos, navegación y arranque; 46 paquetes CSS verificados. No se atribuye una mejora de velocidad a este arreglo de cálculo. |
| Otros módulos e infraestructura | 123 | 39 | Incluye despliegue, marketing, kiosco y servicios auxiliares; consultar los archivos `tests/test_*.py` para alcance exacto. |

Se regeneraron localmente los CSS para normalizar finales de línea de Windows;
no hay diferencias de contenido versionado ni cambios visuales en esta entrega.

## Compatibilidad SQL: pendientes confirmados

Se compararon 425 nombres de procedimientos referenciados por Python con 459
procedimientos instalados. La comparación de firmas usó llamadas cuyos argumentos
pueden contarse estáticamente; no constituye ejecución de todas las rutas.

1. Inventario tiene cuatro firmas antiguas: actualizar materia prima acepta 4
   parámetros frente a 6 del código; crear proveedor 2 frente a 3; actualizar
   proveedor 3 frente a 4; insertar compra 7 frente a 9. También faltan
   `sp_ObtenerEstadoMateriaPrimaParaEdicion` y `sp_ObtenerCompraPorIdempotencia`.
   Faltan las columnas RUC de proveedor e IdempotencyKey/ProveedorRUC de compras.
   Se preparó `database/migrations/20261106_inventory_contracts.sql` con ocho SP
   tomados de las últimas definiciones existentes en el repositorio, columnas
   condicionales y el índice de idempotencia. **No aplicado ni validado en SQL QA.**
   El despliegue web no lo ejecuta. Requiere QA y autorización específica.
2. La estadística de regresión recibe un argumento, pero la versión instalada
   define FechaInicio/FechaFin opcionales y el código envía la fecha de hoy.
   No es un error por exceso de argumentos; necesita revisar el intervalo real
   de 30 días antes de certificar el pronóstico.
3. `seguridad.sp_PruebaAlertaSMTP` y `crm.sp_WhatsAppDatosAviso` no están instalados.
   Son rutas de prueba SMTP y metadatos auxiliares de avisos; no se ejecutaron
   envíos para probarlos. La reparación previa de cotizaciones usa directamente
   `crm.sp_WhatsAppNotificar` y no depende del segundo procedimiento.
4. Los nombres de procedimientos terminados en Sqlite de contabilidad corresponden
   a alternativas de pruebas; no deben instalarse en Azure SQL por esta comparación.
5. `contabilidad.sp_MarcarAsientoAnulado` tiene un cuarto parámetro opcional; sus
   tres argumentos actuales no demuestran una incompatibilidad de cantidad.

No es correcto afirmar que todas las funciones del sistema funcionan: quedan
operaciones de integración SQL y servicios externos sin validar, y las diferencias
de inventario impiden certificar ese módulo. No se sustituyeron SP por consultas
privilegiadas ni se descartaron parámetros para ocultar estas incompatibilidades.

## Entrega

Reparación de planilla lista para CI, revisión e integración en main. El estado
final del workflow y del despliegue se informa con los identificadores de GitHub
una vez terminados. La migración de inventario se entrega únicamente para revisión.
