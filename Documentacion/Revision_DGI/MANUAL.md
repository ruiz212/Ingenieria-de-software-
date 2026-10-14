# Manual complementario de operación y despliegue

Versión: revisión fiscal de octubre de 2026. Este manual describe las funciones
agregadas, sus límites y su activación. Se complementa con los manuales previos
del proyecto y la [revisión técnica](REVISION.md).

## Usuario administrador

1. Abra **Control fiscal**. Mantenga régimen **Pendiente** para pruebas. Complete
   los datos del emisor con los de su inscripción. Antes de cambiar el régimen,
   confirme la documentación real con el responsable tributario.
2. Clasifique cada producto: 15% o 0% con fundamento cuando corresponda. No marque
   todos los productos a 15% por defecto. En régimen general, el sistema rechaza
   ventas de productos sin clasificación. La configuración no determina por sí
   sola el derecho a una exención.
3. Registre precios y extras en el catálogo. Los cambios se aplican a nuevas
   ventas; los documentos ya emitidos conservan sus valores.
4. En POS revise productos y cantidades, seleccione pago y registre la referencia
   de transferencia. El sistema calcula el cambio y convierte USD según la tasa
   configurada. Revise diariamente esa tasa antes de cobrar.
5. Si falla la conexión al confirmar, reintente desde el mismo carrito: se utiliza
   la misma clave mientras la solicitud siga pendiente. No cree manualmente otra
   venta para resolver un resultado incierto; consulte primero el control fiscal.
6. Use **Original y copia** para imprimir. Las anulaciones requieren motivo,
   revierten el asiento y registran la devolución. Ejecute la entrega material del
   dinero o gestión bancaria correspondiente y conserve su soporte: el sistema
   no mueve fondos en el banco. No anule cobros de otro turno ya cerrado.
7. El CSV contiene el registro de facturas del período, incluso anuladas. Es
   apoyo para conciliación y preparación de reportes, no una declaración enviada.

## Caja, compras, producción y nómina

- Caja: el cajero registra su conteo y un supervisor diferente lo verifica. Las
  diferencias significativas requieren explicación. No se venden ni anulan
  documentos mientras haya arqueo pendiente.
- Compras: indique comprobante, cantidad, costo total e IVA respaldado. En cuota
  fija/Pendiente indique cero como crédito fiscal y registre el costo completo.
  En régimen general el responsable debe verificar la procedencia del crédito.
  Las compras se registran por defecto a crédito; el pago posterior al proveedor
  requiere su control contable correspondiente.
- Producción: defina una receta positiva antes del lote. Una falta de insumos
  cancela toda la operación; no queda un lote parcial confirmado.
- Nómina: use el primer y último día del mismo mes. Revise salario, asistencia,
  deducciones y parámetros antes de generar. El lote calcula empleados activos
  sin horas extras; para casos especiales use el cálculo individual. La nómina
  queda **Contabilizada** y no equivale a que el sueldo ya se haya pagado. No
  genere una segunda nómina para corregir la primera.
- Empleados: suspender conserva historial y retira la entrada de la caché facial.
  Los vales se descuentan mediante nómina; no se alterna su estado manualmente.
- Cierre mensual: revise diario, mayor, balance, resultados y balanza. El cierre
  bloquea el período pasado si no hay borradores/asientos descuadrados. No genera
  automáticamente un cierre anual ni presenta impuestos.

## Manual técnico: instalación y migración

Componentes: Flask, pyodbc, SQL Server, plantillas Jinja y JavaScript/CSS. Las
operaciones críticas comparten transacción entre documento, pagos, asiento y
auditoría. Los errores revierten la transacción.

La migración nueva presupone las tablas existentes del proyecto, contabilidad
V1/V2, RRHH, turnos y arqueos. No es un instalador de toda la base desde cero.

1. Detenga escrituras en una ventana de mantenimiento y conserve una copia del
   código anterior. Verifique respaldo/restauración antes de modificar la base.
2. Prepare un entorno Python con `requirements.txt` y controlador ODBC 17.
   Configure de forma privada `DB_CONNECTION_STRING` y una `SECRET_KEY` estable.
3. Desde la raíz del repositorio, con la conexión ya definida en el entorno:

   ```powershell
   python scripts/migrate_fiscal.py --connection-env DB_CONNECTION_STRING
   ```

   El script no carga `.env` automáticamente ni imprime la conexión. Agrega
   columnas, secuencia, auditoría, índices y protecciones; amplía los estados
   permitidos de nómina. Ante un error revierte la transacción. Si existen
   duplicados, deténgase y concilie el origen: no los renumere ni elimine sin
   revisión. Puede volver a ejecutar la migración; conserva la configuración y
   los correlativos existentes.

4. Active simultáneamente esta versión del código. No ejecutar el esquema de
   instalación sobre una base existente. Pruebe primero en una copia aislada.
5. Para desarrollo use `python run.py`. En producción use WSGI y HTTPS; configure
   `SESSION_COOKIE_SECURE=True`. No active depuración pública. Compruebe la hora
   del servidor y la base para la operación de Nicaragua.
6. Verifique inicio de sesión, CSRF, nueva venta, impresión, registro contable,
   anulación de prueba, conteo y permisos. No use registros reales como pruebas.

Si falla una activación, detenga nuevas escrituras y evalúe la causa. No restaure
encima de una base que recibió operaciones posteriores sin conciliarlas. La
recuperación debe probarse en otra base y conservar evidencias del incidente.

## Respaldo y restauración

Para SQL Server instalado en un equipo, el script siguiente crea un archivo
único, usa COPY_ONLY/CHECKSUM y ejecuta VERIFYONLY. La ruta pertenece al servidor
SQL y debe existir con permiso para su cuenta de servicio:

```powershell
python scripts/backup_database.py --connection-env DB_CONNECTION_STRING --directory D:\Respaldos
```

No sobrescribe respaldos ni borra versiones anteriores. El operador debe definir
ejecución diaria, custodia, almacenamiento separado y retención. Este trabajo no
creó una tarea programada. Conserve también código, manuales y los archivos
necesarios de la aplicación; los secretos deben almacenarse de forma protegida.
Registre fecha, responsable, resultado y ubicación. Pruebe periódicamente una
restauración en otra base y compare documentos, correlativos y balanza.

En **Azure SQL Database**, use los respaldos administrados y restauración a un
punto en el tiempo; el script `.bak` rechaza ese motor. Azure administra los
respaldos completos, diferenciales y de transacciones, cuya restauración depende
de la retención. Verifique la política real de la suscripción y una restauración
en otra base. Esta revisión no verificó esos ajustes ni creó una restauración.
Fuente: [Microsoft, respaldos automáticos de Azure SQL Database](https://learn.microsoft.com/en-us/azure/azure-sql/database/automated-backups-overview?view=azuresql).

## Contingencia propuesta

Ante una caída, registre inicio y responsable del incidente, último documento
confirmado y caja afectada. Utilice únicamente el procedimiento y documentos de
contingencia autorizados para el contribuyente; conserve originales, copias y
los anulados. No invente números ni emita pruebas como documentos fiscales.

Al recuperar servicio, concilie efectivo, transferencias, documentos manuales y
operaciones pendientes antes de reabrir caja. Identifique cada documento de
contingencia para impedir duplicidades. La aplicación todavía no ofrece una
importación fiscal de contingencia ni un mecanismo de sustitución automática:
la incorporación requiere revisión y registro contable por el responsable.

## Bitácora y expediente

Conserve capturas y reportes firmados cuando corresponda, pruebas de restauración,
manuales, versión del código, datos del proveedor y comunicaciones de autorización.
La bitácora incluye emisión, anulaciones, asientos y cambios fiscales/de acceso.
No registra todos los accesos de lectura ni sustituye la auditoría del servidor.
