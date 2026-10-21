# Entrega del incremento DGI

**Actualización:** esta entrega documenta la versión inicial 1.0. Consulte
[la revisión funcional 1.1](REVISION_FUNCIONAL.md) para el análisis con perfil
pendiente, permisos operativos de Admin, diagnóstico sin aprobación, fechas y
resultados de la nueva regresión. Las cifras y archivos de ejemplo de abajo se
conservan como evidencia de la entrega original.

Fecha: 15 de octubre de 2026, Nicaragua. Proyecto: Brajher’s Cake.

## Qué se encontró

Aplicación real Flask/SQL Server, autenticación por roles, CSRF, ventas con
instantánea fiscal, compras por materia prima y mayor contable. Ya existía una
pantalla de control fiscal y un CSV auxiliar, pero no diagnóstico preventivo
versionado por período, aprobación de un snapshot ni XLSX interno trazable.
Había cambios locales anteriores en varios módulos y documentos; se conservaron.
La conexión Azure respondió a lectura de metadatos; no se ejecutaron migraciones
ni escrituras de negocio en esa conexión.

## Qué se implementó

- Menú **DGI / Gestión tributaria**, perfil compartido y períodos de preparación.
- Adaptadores de ventas, detalle, compras/proveedores y asientos/cuentas reales.
- Reglas internas: integridad de importes, aritmética y detalle, soportes,
  duplicados sospechosos, vigencia del perfil, estados y conciliación.
- Anulaciones del mismo período, originales/reversiones contables y bloqueo de
  casos entre períodos que necesitan un ajuste revisado.
- Snapshot canónico, SHA-256, versiones y diagnóstico reproducible con Decimal.
- Fuentes consultables, filtros de hallazgos, observaciones y revisión humana.
- Aprobación, exportación y cierre/reapertura con permisos separados por rol.
- Caducidad de aprobación y descarga cuando cambian datos, perfil o motor.
- XLSX interno con seis hojas, texto literal seguro, archivo conservado y SHA-256.
- Auditoría fiscal reutilizada, con UTC explícito y presentación en Nicaragua.
- Migración aditiva idempotente; reversión vacía y rechazo con datos de historial.
- Demo sintética, lanzador local QA y creación opcional de cuenta aleatoria de QA.
- Manual, esquema/diagramas, matriz normativa, trazabilidad y estimación incremental.

El código agrega cuatro tablas, trece rutas DGI y cinco plantillas dentro del
administrador. No crea otra aplicación. Los scripts locales cargan la misma
factoría `create_app` y conservan el inicio de sesión normal.

## Archivos de este incremento

| Uso | Archivos nuevos |
|---|---|
| Rutas | `app/admin/routes_dgi.py` |
| Servicios | `app/services/dgi_engine.py`, `dgi_repository.py`, `dgi_excel.py` |
| Base de datos | `scripts/migrate_dgi.py` |
| Ejecución y demo | `scripts/demo_dgi.py`, `scripts/run_dgi_local.py`, `scripts/estimate_dgi.py` |
| Pantallas | `templates/admin/dgi/layout.html`, `dashboard.html`, `review.html`, `source.html`, `message.html` |
| Estilo y filtros | `static/css/pages/dgi.css`, `static/js/dgi.js` |
| Pruebas | `tests/test_dgi_engine.py`, `tests/test_dgi_sql.py`, `requirements-dev.txt` |
| Documentación | Los siete Markdown de `docs/dgi/`, más `ejemplo/DGI-INTERNO-DEMO.xlsx` y `ejemplo/RESULTADO_DEMO.json` |

Se ampliaron `app/admin/__init__.py`, `templates/admin/sidebar.html`,
`templates/admin/fiscal.html`, `README.md` y `Requerimientos_Panaderia_Amada_V2.md`.
El estado Git contiene además modificaciones anteriores que no pertenecen a este
incremento. No se hizo commit, push ni se publicaron cambios.

## Cómo ejecutarlo

Use las instrucciones completas de [MANUAL.md](MANUAL.md). En este equipo:

```powershell
cd 'C:\Ingenieria de software\panaderia_amada'
$env:TEST_DB_CONNECTION_STRING='DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaQA_Prevalidacion_20261015;Trusted_Connection=yes;TrustServerCertificate=yes;'
python scripts/migrate_dgi.py --connection-env TEST_DB_CONNECTION_STRING
python scripts/run_dgi_local.py --connection-env TEST_DB_CONNECTION_STRING
```

La base local independiente se creó restaurando una copia COPY_ONLY/CHECKSUM de
la base QA preexistente. No se clonaron datos de Azure. El servidor local usa
`127.0.0.1:5065`. Hay una cuenta QA sintética independiente para comprobar el
inicio de sesión real. Su acceso está en `scratch/ACCESO_DGI_LOCAL.txt`, excluido
de Git; no contiene credenciales de la empresa ni de Azure. También puede crear
otra cuenta con `--crear-usuario-demo` en el lanzador, solo en bases QA.

La configuración habitual `.env` no se modificó. El arranque habitual contra
Azure mostrará la necesidad de instalar la migración DGI hasta que un responsable
autorice y ejecute esa fase.

## Demostración realizada

Mes sintético **10/2030**, período **37**:

| Revisión | Base de ventas | Ingresos contables | Diferencia | Errores bloqueantes |
|---|---:|---:|---:|---:|
| #52, versión 1 | C$120000 | C$110000 | C$10000 | 1 |
| #53, versión 2, con ajuste sintético | C$120000 | C$120000 | C$0 | 0 |

La primera revisión se conserva como obsoleta. La segunda fue revisada, aprobada
y exportada utilizando endpoints reales y una sesión iniciada por formulario con
cuenta QA SuperAdmin. La descarga también se comprobó en navegador. El Excel de
ejemplo contiene los bytes de la exportación conservada en SQL Server; su huella
figura en [RESULTADO_DEMO.json](ejemplo/RESULTADO_DEMO.json).

La diferencia de C$10000 es un hallazgo de conciliación; no se convierte en impuesto
ni multa. Permanecen observaciones informativas por la identificación fiscal de
proveedores no disponible y por revisión normativa pendiente.

## Validación

Comando de regresión completa:

```powershell
python -m pytest -q --junitxml=scratch/dgi-tests.xml
```

El resultado de cierre se registra debajo. La suite incluye las pruebas anteriores
del sistema y las nuevas unitarias/SQL DGI. Se ejecutó exclusivamente sobre la base
local QA con datos ficticios. El XML de ejecución permanece en `scratch/`.

**Resultado final: 119 pruebas aprobadas, 0 fallidas, 0 errores y 0 omitidas en
50.93 segundos.** Hubo una advertencia de deprecación de `datetime.utcnow()` en
la dependencia preexistente Flask-Login al comprobar el login; no impidió el flujo.

Comprobaciones adicionales realizadas:

- Compilación de Python y de las cinco plantillas Jinja nuevas; JS sin errores de sintaxis.
- Navegador Edge: login normal de cuenta QA, filtros, aprobación deshabilitada ante
  hallazgos y descarga del XLSX aprobado.
- Vista de escritorio 1440 px y móvil 390 px; ancho de documento móvil 390 px,
  sin desbordamiento global. Tablas con desplazamiento horizontal interno.
- Revisión visual de panel/revisión, tema claro y oscuro; se corrigió el contraste
  de enlaces, ayudas y botones secundarios del nuevo módulo en modo oscuro.
- Archivo de ejemplo abierto mediante lector independiente y Artifact Tool;
  seis hojas renderizadas y revisadas, valores/fechas tipados y sin errores de
  fórmula detectados. Los datos de usuario no generan fórmulas ejecutables.
- `git diff --check` de los archivos existentes tocados por este incremento pasa.
  El diff general ya contenía espacios finales en monitor/POS/JS ajenos a este
  trabajo; no se modificaron para esconder esas diferencias.

Durante la regresión se corrigió la restauración del aislamiento de conexiones
ODBC después del diagnóstico, para no propagar SERIALIZABLE al POS. También se
agregó una guarda que impide cambiar desde DGI el régimen compartido sin completar
los datos del emisor requeridos por el POS. La demo solo completa esos datos con
marcas ficticias explícitas, en una base QA.

## Pendientes y límites

**Normativos:** régimen/obligación reales, revisión profesional de reglas,
plantilla y guía vigentes con mapa aprobado. El exportador oficial está bloqueado
en el servidor. Las referencias históricas no acreditan vigencia para 2026.
Consulte [MATRIZ_NORMATIVA.md](MATRIZ_NORMATIVA.md).

**Técnicos posteriores:** importación/conciliación de archivos, diferencias
automáticas campo a campo entre versiones, notas de crédito/débito completas,
ajustes comerciales posteriores al cierre, multiempresa/multisucursal y carga
concurrente de producción. Los datos históricos incompletos generan hallazgos;
no se reconstruye ni certifica retrospectivamente un comprobante ausente.

**Estimación:** se midió el incremento y se documentó un escenario con los
coeficientes históricos. No se inventó una nueva línea base COCOMO validada;
requiere conteo comparable y aprobación de los supuestos. Consulte [COCOMO.md](COCOMO.md).

**Activación externa:** aplicar migración en Azure, configurar operación con datos
reales y publicar requieren una etapa aprobada, respaldo/restauración y revisión
operativa. No se accedió a VET con credenciales, no se declararon impuestos, no se
hicieron pagos y no se alteraron registros fiscales reales.
