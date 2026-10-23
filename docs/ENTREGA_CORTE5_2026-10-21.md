# Entrega Corte 5 — 21 de octubre de 2026

Se implementaron los cuatro ajustes solicitados en la aplicación Flask/SQL Server. No se modificaron definiciones ni escalas salariales. La validación con escrituras se realizó exclusivamente sobre `PanaderiaQA_Prevalidacion_20261015`; no se aplicaron migraciones a la base ordinaria ni se desplegó a Azure.

## Comportamiento implementado

- **DGI:** la vista del período consulta facturas por número, cliente o razón social, estado, fechas y tipo de venta. La consulta se pagina en SQL Server a 10, 25 o 50 filas y usa índices de fecha, número y cliente. Las filas de las últimas 24 horas se distinguen visualmente. El listado se puede actualizar sin recargar la aplicación; también se consulta al volver a la pestaña y cada 30 segundos mientras está visible.
- **Sesión y formularios:** el reloj de inactividad se renueva mediante `/auth/ping` cuando hubo actividad humana reciente. Un diálogo advierte dos minutos antes del vencimiento. Los formularios de empleado, perfil DGI y cotización recuperan borradores de la pestaña y advierten antes de salir con cambios sin guardar. La renovación del token CSRF acompaña las sesiones largas. Se deshabilitó el inicio automático mediante cookie «recordarme» para que no eluda el vencimiento.
- **RR. HH.:** la fecha de ingreso usa calendario y se inicia con la fecha comercial actual. El catálogo `rrhh.PerfilesPuesto` conserva descripción, obligaciones y competencias por cargo; los cargos históricos se incorporan con fichas pendientes de completar. El formulario permite registrar un empleado sin fotografía. Si el reconocimiento facial falla, Admin o SuperAdmin puede registrar entrada o salida indicando un motivo; supervisor y motivo quedan auditados en la misma transacción del marcaje.
- **Contabilidad y caja:** los asientos de anticipos y liquidaciones muestran leyendas explícitas. Se verificó que el débito se distribuya entre Caja/Banco y Encargos por Cobrar según el importe cobrado y que el anticipo aparezca de inmediato en el arqueo del turno receptor, aun si el encargo continúa pendiente de entrega.

## Evidencia de validación

- Suite completa con base QA y SMTP bloqueado: **428 pruebas aprobadas**, comando `scratch/remediation_20261017/venv/Scripts/python.exe scratch/remediation_20261020/run_tests.py`. Registro: `scratch/remediation_20261020/corte5-full-verified.log`.
- Pruebas dirigidas de los cuatro módulos, páginas con roles reales y caja: **34 aprobadas**.
- Navegador: **3 casos** de búsqueda DGI, borradores y aviso de sesión; **2 casos** adicionales de seguridad de contenido web. Se ejecutaron por separado tras observar interferencia al iniciar dos navegadores simultáneamente.
- CSS: **43 paquetes verificados** con `scripts/build_css.py --check`; `git diff --check` salió sin errores de espacios.
- Migraciones `01`–`04` aplicadas y repetidas sobre la **base QA** sin error; el segundo pase verificó idempotencia. La migración agrega el catálogo y los índices, y el procedimiento fiscal paginado.

## Activación pendiente fuera de QA

Antes de usar estos cambios en Azure App Service sin Docker, aplicar las migraciones `database/01_esquemas_migracion.sql` a `database/04_alertas_outbox.sql` a la base de destino, desplegar los archivos estáticos generados y repetir las pruebas de acceso con roles reales. También siguen pendientes las tareas operativas de la entrega anterior: configurar/registrar el trabajador SMTP independiente y reconciliar los pagos históricos de caja con evidencia. Esta entrega no realizó envíos SMTP reales, despliegue ni cambios a la base ordinaria.
