# Instalar, ejecutar y demostrar el módulo DGI

El módulo forma parte del sistema Flask existente. Ingrese con una cuenta Admin
o SuperAdmin y abra **DGI / Gestión tributaria** en el menú. Ruta: `/admin/dgi`.
La nueva opción también se encuentra en Control fiscal.

Versión funcional 1.1: el análisis interno admite perfil fiscal pendiente. Las
revisiones anteriores se conservan; use **Revalidar fuentes** para aplicar las
nuevas reglas y la lectura de fechas. Consulte [la revisión funcional](REVISION_FUNCIONAL.md).

## Instalación en una base de desarrollo

Abra PowerShell en `C:\Ingenieria de software\panaderia_amada`.

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Conserve la conexión de producción en su configuración actual. Para probar este
incremento utilice una base de desarrollo que ya tenga el esquema y las
migraciones fiscales/contables previas. **No ejecute `database/esquema.sql` sobre
una base con datos que deba conservar.** Ese archivo reconstruye el esquema.

En esta entrega se preparó una copia local independiente con datos de QA:

```powershell
$env:TEST_DB_CONNECTION_STRING='DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaQA_Prevalidacion_20261015;Trusted_Connection=yes;TrustServerCertificate=yes;'
python scripts/migrate_dgi.py --connection-env TEST_DB_CONNECTION_STRING
python scripts/run_dgi_local.py --connection-env TEST_DB_CONNECTION_STRING
```

Abra `http://127.0.0.1:5065/admin/dgi` e inicie sesión con una cuenta administrativa
de esa base QA. El lanzador no omite autenticación, no aplica migraciones y
rechaza bases cuyo nombre no empiece por `PanaderiaQA_`. El módulo de producción
no depende de este lanzador ni de scripts de demostración.

Si necesita una cuenta independiente de prueba, agregue `--crear-usuario-demo`
al comando del lanzador. Crea un usuario sintético SuperAdmin con una contraseña
aleatoria mostrada una sola vez en la consola, exclusivamente en la base QA.
No cambia cuentas anteriores ni crea contraseñas predeterminadas en el código.

En otra máquina adapte el servidor y nombre de la base aislada. Crear una nueva
base y cargar el esquema no es parte de la migración DGI. Consulte el README y
el manual fiscal anterior para los prerrequisitos contables/fiscales.

Para usar posteriormente la instalación habitual (`python run.py`) con otra base,
el administrador debe aplicar la migración contra la misma conexión que utiliza
la aplicación. Esta entrega **no migró Azure ni publicó cambios**. Si falta la
migración, la pantalla DGI muestra HTTP 503 con una explicación, sin instalar
tablas automáticamente.

## Uso diario

1. **Guardar avance del perfil:** razón social, RUC según inscripción, régimen declarado,
   responsable, obligación y fechas de vigencia pueden quedar pendientes. No se valida un
   formato fiscal universal de RUC. Los datos del emisor se comparten con
   Facturación: cambiar el régimen afecta las nuevas ventas.
   Si faltan razón social, RUC, dirección, teléfono o referencia de autorización, el régimen activo
   se rechaza y debe completar primero el emisor en Control fiscal; no se dejan
   incompletos los prerrequisitos del POS.
2. **Abrir mes:** seleccione un mes. Si ya existe, se reutiliza. No cambia el
   estado del período contable.
3. **Analizar:** seleccione la obligación o propósito y pulse Analizar período.
   Consulte ventas, compras y trazabilidad del mayor. Un período sin operaciones
   muestra ceros registrados y límites, sin inventar impuestos.
4. **Revisar hallazgos:** filtre severidad/regla, abra el documento y revise la
   acción indicada. Las observaciones son seguimiento. No reemplazan soportes ni
   permiten saltarse errores. DGI no modifica facturas, stock o asientos.
5. **Corregir y revalidar:** haga el ajuste autorizado en su módulo propietario.
   Facturas emitidas no se editan. Si falta un flujo de nota de crédito/débito,
   conserve el bloqueo y solicite revisión contable. Revalidar conserva versiones.
6. **Registrar revisión humana:** describa documentos, conciliación, supuestos y
   advertencias revisados, incluso si no hay errores.
7. **Validar internamente:** Admin o SuperAdmin verifica que no existan errores
   de datos y valida la revisión. Un perfil fiscal pendiente no bloquea esta
   validación interna ni la convierte en aprobación tributaria. Se registran
   identidad y fecha; no hay segregación obligatoria de dos personas.
8. **Exportar:** el **diagnóstico sin aprobación** se descarga incluso con
   errores y registra usuario y SHA-256 en auditoría, sin cambiar el estado. El
   **informe validado** requiere revisión humana, cero errores bloqueantes y
   aprobación vigente; se conservan sus bytes exactos. Repetirlo devuelve el
   mismo archivo. Si cambian datos, perfil o motor, debe revalidar.
9. **Cerrar preparación:** Admin o SuperAdmin puede cerrar cuando las últimas revisiones
   estén aprobadas y vigentes. Puede reabrir sin eliminar historial.

Las horas nuevas DGI se guardan en UTC y se muestran con hora de Nicaragua.
Las ventas, compras y anulaciones nuevas guardan la misma hora de Nicaragua que
su asiento, aunque Flask y SQL estén en zonas distintas. Un histórico con desfase
de seis horas se interpreta por su recibo solo si concuerda con el asiento o
incluye zona explícita; se conserva y muestra la fecha original. No se reescriben
documentos históricos ni se adivina una zona sin evidencia.

## Demostración de cinco minutos para el profesor

El script solo admite una base `PanaderiaQA_`. Crea tres documentos sintéticos
de C$40000 cada uno, una compra sintética de C$5000 y un asiento de ingresos de
C$110000. Utiliza un mes vacío y modifica solo el perfil de la base de prueba.
No representa una empresa inscrita, una operación fiscal real ni una tasa oficial.

```powershell
python scripts/demo_dgi.py --connection-env TEST_DB_CONNECTION_STRING --mes 2030-10
```

La salida muestra `periodo_id` y `revision_id`. El período de 2030 es deliberadamente
ficticio para separar la demo de los registros habituales. Si ya contiene datos,
el script se detiene: elija otro mes vacío. No lo ejecute para reiniciar/borrar
una demostración existente.

1. Abra esa revisión: base C$120000, ingresos contables C$110000, diferencia
   C$10000. Muestre el hallazgo CONCILIACION y el bloqueo de aprobación/exportación.
2. Abra las tres facturas y el asiento para explicar el origen de las cifras.
3. Registre una observación sobre el documento faltante.
4. Para simular la corrección, use el ID de período mostrado en el primer comando:

```powershell
python scripts/demo_dgi.py --connection-env TEST_DB_CONNECTION_STRING --corregir-periodo ID
```

Se agrega un asiento de ajuste sintético de C$10000 a través del servicio contable
existente; no cambia los importes de facturas. La corrección se limita a los
documentos reconocidos como DEMO-DGI y rechaza otros importes/casos.

5. Abra la nueva versión: ingresos C$120000, diferencia cero; la anterior permanece
   en el historial. Registre la revisión humana y valide con Admin o SuperAdmin.
6. Descargue y abra el XLSX: Resumen, Ventas, Compras, Hallazgos, Trazabilidad y
   Supuestos. Señale el rótulo no oficial y explique por qué la opción oficial
   permanece deshabilitada.

La muestra entregada en `docs/dgi/ejemplo/` proviene del flujo de exportación con
datos sintéticos corregidos. El caso inicial de diferencia se conserva como
evidencia en la base QA y en el informe de demostración.

## Pruebas y reversión

```powershell
python -m pytest tests/test_dgi_engine.py -q
python -m pytest tests/test_dgi_sql.py -q
python -m pytest -q
python scripts/estimate_dgi.py
python scripts/audit_dgi_readonly.py --connection-env DB_CONNECTION_STRING --mes 2026-10
```

La suite SQL requiere una base aislada con los datos y migraciones previas. Inserta
solo datos ficticios. Las pruebas de migración crean una base efímera propia y
comprueban subida, repetición, reversión vacía y rechazo de reversión con datos.

```powershell
python scripts/migrate_dgi.py --connection-env TEST_DB_CONNECTION_STRING --down
```

La reversión se deniega si existe cualquier período, revisión, observación,
exportación o un perfil DGI configurado. En una base utilizada, conserve esquema
e historial y retire el acceso desde la aplicación si fuera necesario; no borre
evidencia para forzar una reversión.

Antes de producción quedan pendientes respaldo/restauración, revisión de carga,
zona horaria comercial, autorizaciones SQL, validación tributaria profesional y
aprobación expresa para migrar/publicar. No se solicitan ni almacenan claves VET.
