# 🗄️ Base de Datos — Panadería y Repostería Brajher's Cake (`PanaderiaDB`)

## Descripción General

Esta carpeta contiene el diseño relacional empresarial en **Tercera Forma Normal (3FN)** para SQL Server, estructurado en **8 esquemas de dominio**, **6 roles nativos de base de datos (RBAC)** con encadenamiento de propiedad (*Ownership Chaining*), **Procedimientos Almacenados (`sp_...`)** para consulta y operación transaccional, **Dynamic Data Masking (DDM)**, **Triggers de Inmutabilidad** y **Bitácora de Errores con Alertas SMTP**.

---

## 📂 Archivos SQL del Módulo

| Archivo | Propósito |
|---------|-----------|
| `esquema.sql` | Script base inicial de tablas maestras, relaciones e inserción de datos semilla |
| `01_esquemas_migracion.sql` | Creación de los **8 esquemas**, tablas de seguridad (`BitacoraErrores`, `BloqueosCuenta`), transferencia idempotente de las 50 tablas a su esquema de dominio, sinónimos en `dbo` y triggers de inmutabilidad |
| `02_roles_y_seguridad_bd.sql` | Creación de los **6 roles nativos de BD** (`CREATE ROLE`), usuarios contenidos (`WITHOUT LOGIN`), **Dynamic Data Masking (DDM)** y `DENY SELECT/INSERT/UPDATE/DELETE` directo sobre tablas |
| `03_stored_procedures.sql` | Catálogo de **Procedimientos Almacenados (`sp_...`)** por esquema con `BEGIN TRY ... BEGIN CATCH`, registro automático en `seguridad.BitacoraErrores` y permisos granulares `GRANT EXECUTE` por rol |

Para aplicar o actualizar toda la arquitectura desde línea de comandos:
```bash
python scripts/migrate_esquemas_roles_sp.py --connection-env DB_CONNECTION_STRING
```

---

## 🏛️ Arquitectura de 8 Esquemas de Dominio

| # | Esquema | Propósito | Tablas Principales |
|---|---------|-----------|--------------------|
| 1 | `seguridad` | Autenticación, RBAC, 2FA, Auditoría, Errores y Bloqueos | `Roles`, `Usuarios`, `AuthChallenges`, `AuditLog`, `ConfiguracionSistema`, `BitacoraErrores`, `BloqueosCuenta` |
| 2 | `crm` | Fidelización, Cartera de Clientes y Cotizaciones Web | `NivelesConfianza`, `Clientes`, `Cotizaciones` |
| 3 | `catalogo` | Productos Comerciales, Categorías, Unidades e Ingredientes | `Categorias`, `UnidadesMedida`, `Productos`, `Ingredientes` |
| 4 | `ventas` | Punto de Venta (POS), Facturación, Pagos, Encargos y Arqueos | `TurnosCaja`, `Facturas`, `DetalleFacturas`, `DetalleIngredientes`, `Pagos`, `FacturasRUC`, `Encargos`, `ArqueoCaja`, `ArqueoDetalleDenominacion`, `ArqueoAuditLog`, `TipoCambio`, `SecuenciasFiscales` |
| 5 | `produccion` | Inventario de Insumos, Proveedores, Recetas, Lotes y Mermas | `Proveedores`, `MateriaPrima`, `ComprasMateriaPrima`, `RecetaProducto`, `ProduccionLotes`, `ConsumoLote`, `Mermas` |
| 6 | `rrhh` | Recursos Humanos (Ley 185 / Ley 822 Nicaragua) y Biometría | `Empleados`, `TurnosLaborales`, `Asistencia`, `FeriadosNacionales`, `Nomina`, `DetalleNomina`, `LicenciasEmpleados`, `DeduccionesJudiciales`, `IncidentesLaborales`, `ValesEmpleados` |
| 7 | `contabilidad` | Contabilidad NIIF por Partida Doble, CxC, CxP y Conciliación | `CatalogoCuentas`, `PeriodosContables`, `TiposComprobante`, `AsientosDiario`, `DetalleAsientos`, `EgresosPrivados`, `CuentasPorCobrar`, `CuentasPorPagar`, `PagosCxC`, `ConciliacionBancaria`, `DetalleConciliacion` |
| 8 | `fiscal` | Trazabilidad Fiscal Inmutable y Preparación Tributaria DGI | `BitacoraFiscal`, `DGI_Periodos`, `DGI_Revisiones`, `DGI_Observaciones`, `DGI_Exportaciones` |

---

## 🔐 Matriz de 6 Roles de Base de Datos (Menor Privilegio)

| Rol SQL Server | Rol Aplicación | Acceso a Tablas Base | Permisos sobre Stored Procedures (`EXECUTE`) |
|----------------|----------------|----------------------|----------------------------------------------|
| `db_rol_superadmin` | `SuperAdmin` | `DENY DELETE` en `fiscal`, `contabilidad`, `AuditLog`, `BitacoraErrores` | `GRANT EXECUTE` en los 8 esquemas + `UNMASK` |
| `db_rol_gerencia` | `Admin` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | `GRANT EXECUTE` en `crm`, `catalogo`, `ventas`, `produccion`, `rrhh`, `contabilidad`, `fiscal` (`DENY` en `sp_ListarAuditoria` y `sp_ListarBitacoraErrores`) |
| `db_rol_cajero_pos` | `Estandar` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Solo SPs de POS (`ventas`), catálogo activo (`catalogo`), clientes/cotizaciones (`crm`), monitor y mermas (`produccion`) |
| `db_rol_produccion` | `Operativo` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Solo SPs de `produccion` (monitor, lotes, recetas, inventario, mermas) y lectura de `catalogo` |
| `db_rol_kiosco` | Kiosco Biométrico | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Exclusivamente `rrhh.sp_ObtenerDescriptoresFacialesKiosco`, `rrhh.sp_RegistrarMarcajeKiosco` y `rrhh.sp_ObtenerResumenAsistencia` |
| `db_rol_portal_cliente` | `Cliente` / `Invitado` | `DENY SELECT, INSERT, UPDATE, DELETE` directo | Exclusivamente `catalogo.sp_ObtenerCatalogoActivo`, SPs de cotizaciones propias en `crm` y `ventas.sp_ConsultarSeguimientoPedido` |
