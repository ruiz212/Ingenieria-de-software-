# Revisión funcional DGI 1.1

Fecha: 15/10/2026, Nicaragua. Refinamiento solicitado después de probar el módulo.
El usuario eligió análisis interno con configuración fiscal pendiente y diagnósticos
rotulados. No se trasladan obligaciones oficiales a una instalación de pruebas.

## Resultado del caso aportado

Los tres documentos de octubre suman **C$46.00** y sus ingresos contables suman
**C$46.00**. La diferencia es cero. El error del diagnóstico 1.0 procedía del
perfil fiscal vacío, no de una suma incorrecta. La ausencia de compras y de una
plantilla oficial eran información contextual. La versión 1.1 separa los tres
grupos: errores/advertencias de datos, configuración pendiente y contexto.

La comprobación de las fuentes configuradas se hizo **solo mediante lectura**:

| Mes | Base de ventas | Ingresos contables | Errores de datos | Advertencias | Causa identificada |
|---|---:|---:|---:|---:|---|
| 08/2026 | C$1143.00 | C$0.00 | 2 | 6 | Falta mayor para las ventas y hay diferencia; seis documentos históricos sin instantánea |
| 09/2026 | C$553.00 | C$51.00 | 39 | 12 | 38 compras sin número de comprobante, diferencia de ingresos y doce documentos sin instantánea |
| 10/2026 | C$46.00 | C$46.00 | **0** | **0** | Datos del mes coherentes; tres fechas históricas interpretadas con evidencia |

Los registros antiguos incompletos se conservan. No se inventaron asientos,
comprobantes, RUC ni importes para borrar alertas. El nuevo diagnóstico se puede
descargar con errores, siempre indicando que no tiene aprobación.

## Fallos corregidos y mejoras

1. **Fechas diferentes entre SQL y Flask.** `Facturas.FechaHora` usaba GETDATE()
   del servidor Azure, mientras el asiento y el recibo usaban hora local. Por
   ejemplo, la factura #23 quedó en BD el 14/10 a las 02:13, aunque el recibo y
   asiento corresponden al 13/10 a las 20:13. Cerca del cambio de mes esto podía
   producir una diferencia de conciliación artificial.
2. **Reloj comercial común.** Facturas, compras y anulaciones nuevas reciben una
   única fecha de Nicaragua que también se pasa al servicio contable. El reloj
   no depende de la zona del host y usa segundos para evitar redondeos de SQL
   DATETIME en el último instante del mes.
3. **Históricos sin reescritura.** El adaptador busca también el día adyacente y
   adopta la fecha del recibo ante un desfase de seis horas solo cuando concuerda
   con su asiento o tiene zona explícita. Sin evidencia suficiente conserva la
   fecha BD y muestra advertencia. Guarda ambas fechas y el criterio; también
   aparecen en las fuentes y en Excel. Las anulaciones se contrastan con su
   reversión cuando existe. No se ejecutaron UPDATE sobre documentos históricos.
4. **Perfil pendiente separado de errores.** El RUC, régimen y demás campos
   fiscales pendientes ya no bloquean el análisis interno. Se puede guardar el
   avance del perfil. Al activar un régimen se conservan las exigencias del POS,
   evitando dejar incompletos sus datos de emisor.
5. **Administrador operativo.** Admin y SuperAdmin pueden revisar, validar,
   exportar y cerrar/reabrir la preparación interna. Se mantienen sesión, CSRF,
   revisión humana, fuentes vigentes, auditoría y bloqueo por errores técnicos.
6. **Dos reportes internos.** Diagnóstico sin aprobación disponible incluso con
   errores; informe validado solo después de revisión y aprobación vigente. El
   diagnóstico registra actor y SHA-256 sin modificar el estado ni fingir una
   aprobación. Las entradas inválidas se identifican como tales en Excel.
7. **Pantallas accionables.** Pasos visibles, contadores correctos, fechas
   legibles, enlaces a la configuración y al documento específico, detalle de
   factura/asiento y últimas revisiones por defecto con acceso al historial.
   No se mezcla una configuración ausente con una diferencia monetaria.
8. **Auditoría repetible.** `scripts/audit_dgi_readonly.py` permite revisar meses
   disponibles sin crear revisiones, editar perfiles ni cambiar registros.

El motor pasa de `dgi-interno-1.0` a `dgi-interno-1.1`. Los snapshots previos no se
reinterpretan ni sobrescriben: **abra la revisión y pulse Revalidar fuentes**.
La nueva versión conserva las anteriores y aplica los criterios actuales. No se
requiere una migración adicional a las tablas DGI ya instaladas.

## Pruebas realizadas

```powershell
$env:TEST_DB_CONNECTION_STRING='DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaQA_Prevalidacion_20261015;Trusted_Connection=yes;TrustServerCertificate=yes;'
python -m pytest -q --junitxml=scratch/dgi-1.1-tests.xml
```

**131 pruebas aprobadas, cero fallidas y cero omitidas, en 35.25 segundos.** Una
advertencia de deprecación de Flask-Login preexistente durante el login; no impide
el flujo. La suite incluye veinte pantallas de módulos anteriores y pruebas de
ventas, reintentos, pagos, compras/stock, anulaciones, partida doble, cierre,
nómina, permisos y DGI.

Cobertura nueva: reproducción exacta de C$46 con perfil vacío y sin compras;
diagnóstico con errores sin alterar su estado; aprobación interna por Admin con
perfil pendiente; rechazo de cambios que dejen incompleto el POS; fecha común
de factura/asiento en el último segundo del mes; selección correcta de un recibo
histórico UTC que cruza de mes sin editar su fuente; y fechas comunes de compras
y anulaciones con sus asientos.

También se comprobó por navegador el caso sintético C$36+C$5+C$5 con una cuenta
**Admin real de QA**, mediante login normal: cero errores/advertencias, perfil
pendiente, diagnóstico descargado, revisión humana, validación e informe final.
Escritorio 1440 px, móvil 390 px sin desbordamiento, tema oscuro legible y cero
errores de JavaScript. El escenario visual está en una base local independiente.

## Repetir la auditoría sin modificar datos

```powershell
python scripts/audit_dgi_readonly.py --connection-env DB_CONNECTION_STRING --mes 2026-10
python scripts/audit_dgi_readonly.py --connection-env DB_CONNECTION_STRING
```

Utiliza una transacción de lectura consistente por mes, sin modificar revisiones,
fuentes ni perfil. La conexión se proporciona por variable de entorno; el reporte
no imprime credenciales ni datos fiscales identificativos. La salida JSON de la
verificación de esta entrega está en `scratch/auditoria_fuentes_dgi_1_1.json`.

## Alcance preservado

No se presentaron declaraciones, hicieron pagos, cambiaron tasas fiscales ni se
validaron créditos tributarios. La exportación oficial sigue bloqueada en servidor.
No se migró ni se alteró la base Azure durante esta revisión; se consultaron sus
fuentes. Las escrituras de pruebas y el caso visual se limitaron a la base local QA.
No se borró el historial de pruebas incompletas de agosto/septiembre.
