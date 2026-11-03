# 🗄️ Base de Datos — Panadería y Repostería Brajher's Cake (`PanaderiaDB`)

## Descripción General

Esta carpeta contiene el diseño relacional empresarial en **Tercera Forma Normal (3FN)** para SQL Server / Azure SQL, estructurado en **8 esquemas de dominio**, **63 tablas**, **7 roles nativos de base de datos (RBAC)** con encadenamiento de propiedad (*Ownership Chaining*), **356+ Procedimientos Almacenados (`sp_...`)** para consulta y operación transaccional, **Dynamic Data Masking (DDM)**, **Triggers de Inmutabilidad** y **Bitácora de Errores con Alertas SMTP**.

---

## 📂 Archivos SQL del Módulo

| Archivo | Propósito |
|---|---|
| `00_init_database_completo.sql` / `esquema.sql` | **Script maestro de inicialización DESDE CERO**. Crea la base de datos, los 8 esquemas, las 63 tablas con PKs/FKs/índices, sinónimos retrocompatibles, triggers de inmutabilidad, matriz RBAC de 7 roles, 356+ Stored Procedures y datos semilla obligatorios (NIIF, escalas salariales, perfiles de puesto, configuración). |
| `01_esquemas_migracion.sql` | Script de migración incremental: Creación de los **8 esquemas**, tablas de seguridad (`BitacoraErrores`, `BloqueosCuenta`), transferencia idempotente de tablas a su esquema de dominio, sinónimos en `dbo` y triggers de inmutabilidad. |
| `02_roles_y_seguridad_bd.sql` | Creación de roles nativos de BD (`CREATE ROLE`), usuarios contenidos (`WITHOUT LOGIN`), **Dynamic Data Masking (DDM)** y `DENY SELECT/INSERT/UPDATE/DELETE` directo sobre tablas base. |
| `03_stored_procedures.sql` | Catálogo completo de **Procedimientos Almacenados (`sp_...`)** por esquema con `BEGIN TRY ... BEGIN CATCH`, registro automático en `seguridad.BitacoraErrores` y permisos granulares `GRANT EXECUTE` por rol. |
| `04_alertas_outbox.sql` | Tablas de cola y deduplicación (`seguridad.AlertasSMTPOutbox`, `AlertasSMTPDedup`), rol de worker (`db_rol_alertas_worker`) y SPs transaccionales de alertas. |
| `05_mercadotecnia.sql` | Instantánea local de recomendaciones, entrenamiento agregado de ventas emitidas y procedimientos con acceso separado para gerencia y portal. |
| `esquema_legacy_20260910.sql.bak` | Respaldo del esquema monolítico inicial (desfasado del 10/09/2026, solo para referencia histórica). |

---

## 🚀 Cómo Inicializar la Base de Datos desde Cero

Para levantar una base de datos completamente nueva (LocalDB, SQL Server 2019/2022 o Azure SQL):
1. Abrir `00_init_database_completo.sql` (o `esquema.sql`) en SQL Server Management Studio (SSMS), Azure Data Studio o VS Code.
2. Ejecutar todo el script (`F5` o mediante `sqlcmd`):
```bash
sqlcmd -S <servidor> -d master -i database/00_init_database_completo.sql
```

Para aplicar o actualizar procedimientos y seguridad en una base de datos ya existente:
```bash
python scripts/migrate_esquemas_roles_sp.py --connection-env DB_CONNECTION_STRING
```

La migración incluye `05_mercadotecnia.sql`. Comprueba el nombre de la base con `--expected-db` al aplicarla en un entorno existente. El primer acceso de gerencia a **Mercadotecnia** entrena el modelo; después se actualiza si han pasado 24 horas al abrir ese panel, o con el botón **Actualizar análisis**. La tienda utiliza el catálogo como alternativa hasta que exista una instantánea.

---

## 🏛️ Arquitectura de 8 Esquemas de Dominio (63 Tablas)

| # | Esquema | Tablas | Propósito | Tablas Principales |
|---|---------|--------|-----------|--------------------|
| 1 | `seguridad` | 9 | Autenticación, RBAC, 2FA, Auditoría, Errores, Bloqueos y Alertas SMTP | `Roles`, `Usuarios`, `AuthChallenges`, `AuditLog`, `ConfiguracionSistema`, `BitacoraErrores`, `BloqueosCuenta`, `AlertasSMTPOutbox`, `AlertasSMTPDedup` |
| 2 | `crm` | 3 | Fidelización, Cartera de Clientes y Cotizaciones Web | `NivelesConfianza`, `Clientes`, `Cotizaciones` |
| 3 | `catalogo` | 4 | Productos Comerciales, Categorías, Unidades e Ingredientes | `Categorias`, `UnidadesMedida`, `Productos`, `Ingredientes` |
| 4 | `ventas` | 12 | Punto de Venta (POS), Facturación, Pagos, Encargos y Arqueos | `TurnosCaja`, `Facturas`, `DetalleFacturas`, `DetalleIngredientes`, `Pagos`, `FacturasRUC`, `Encargos`, `ArqueoCaja`, `ArqueoDetalleDenominacion`, `ArqueoAuditLog`, `TipoCambio`, `SecuenciasFiscales` |
| 5 | `produccion` | 7 | Inventario de Insumos, Proveedores, Recetas, Lotes y Mermas | `Proveedores`, `MateriaPrima`, `ComprasMateriaPrima`, `RecetaProducto`, `ProduccionLotes`, `ConsumoLote`, `Mermas` |
| 6 | `rrhh` | 12 | Recursos Humanos (Ley 185 / Ley 822 Nicaragua), Biometría y Puestos | `Empleados`, `TurnosLaborales`, `Asistencia`, `FeriadosNacionales`, `Nomina`, `DetalleNomina`, `LicenciasEmpleados`, `DeduccionesJudiciales`, `IncidentesLaborales`, `ValesEmpleados`, `escala_salarial`, `PerfilesPuesto` |
| 7 | `contabilidad` | 11 | Contabilidad NIIF por Partida Doble, CxC, CxP y Conciliación | `CatalogoCuentas`, `PeriodosContables`, `TiposComprobante`, `AsientosDiario`, `DetalleAsientos`, `EgresosPrivados`, `CuentasPorCobrar`, `CuentasPorPagar`, `PagosCxC`, `ConciliacionBancaria`, `DetalleConciliacion` |
| 8 | `fiscal` | 5 | Trazabilidad Fiscal Inmutable y Preparación Tributaria DGI | `BitacoraFiscal`, `DGI_Periodos`, `DGI_Revisiones`, `DGI_Observaciones`, `DGI_Exportaciones` |

---

## 🔐 Matriz de 7 Roles de Base de Datos (Menor Privilegio)

| Rol SQL Server | Rol Aplicación | Acceso a Tablas Base | Permisos sobre Stored Procedures (`EXECUTE`) |
|----------------|----------------|----------------------|----------------------------------------------|
| `db_rol_superadmin` | `SuperAdmin` | `DENY DELETE` en `fiscal`, `contabilidad`, `AuditLog`, `BitacoraErrores` | `GRANT EXECUTE` en los 8 esquemas + `UNMASK` |
| `db_rol_gerencia` | `Admin` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | `GRANT EXECUTE` en `crm`, `catalogo`, `ventas`, `produccion`, `rrhh`, `contabilidad`, `fiscal` (`DENY` en `sp_ListarAuditoria` y `sp_ListarBitacoraErrores`) |
| `db_rol_cajero_pos` | `Estandar` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Solo SPs de POS (`ventas`), catálogo activo (`catalogo`), clientes/cotizaciones (`crm`), monitor y mermas (`produccion`) |
| `db_rol_produccion` | `Operativo` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Solo SPs de `produccion` (monitor, lotes, recetas, inventario, mermas) y lectura de `catalogo` |
| `db_rol_kiosco` | Kiosco Biométrico | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Exclusivamente `rrhh.sp_ObtenerDescriptoresFacialesKiosco`, `rrhh.sp_RegistrarMarcajeKiosco` y `rrhh.sp_ObtenerResumenAsistencia` |
| `db_rol_portal_cliente` | `Cliente` / `Invitado` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Exclusivamente `catalogo.sp_ObtenerCatalogoActivo`, SPs de cotizaciones propias en `crm` y `ventas.sp_ConsultarSeguimientoPedido` |
| `db_rol_alertas_worker` | Background Worker SMTP | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Exclusivamente `sp_EncolarAlertaSMTP`, `sp_ReclamarAlertaSMTP` y `sp_MarcarErrorNotificadoSMTP` |
