-- ============================================================================
-- BASE DE DATOS: PanaderiaDB (Brajher's Cake / Panadería Amada)
-- SCRIPT DE INICIALIZACIÓN COMPLETO DESDE CERO
-- Arquitectura: 8 Esquemas de Dominio (3FN), 63 Tablas, RBAC, Triggers, SPs y Semilla
-- Generado automáticamente y validado contra el entorno de producción SQL Server / Azure SQL
-- ============================================================================

SET NOCOUNT ON;
GO

-- 1. CREACIÓN O ACTIVACIÓN DE LA BASE DE DATOS
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = N'PanaderiaDB')
BEGIN
    CREATE DATABASE [PanaderiaDB];
END
GO

USE [PanaderiaDB];
GO

-- ============================================================================
-- 2. CREACIÓN DE LOS 8 ESQUEMAS DE DOMINIO
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'seguridad')
    EXEC('CREATE SCHEMA [seguridad] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'crm')
    EXEC('CREATE SCHEMA [crm] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'catalogo')
    EXEC('CREATE SCHEMA [catalogo] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'ventas')
    EXEC('CREATE SCHEMA [ventas] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'produccion')
    EXEC('CREATE SCHEMA [produccion] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'rrhh')
    EXEC('CREATE SCHEMA [rrhh] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'contabilidad')
    EXEC('CREATE SCHEMA [contabilidad] AUTHORIZATION [dbo]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'fiscal')
    EXEC('CREATE SCHEMA [fiscal] AUTHORIZATION [dbo]');
GO

-- ============================================================================
-- 3. CREACIÓN DE TABLAS MAESTRAS Y TRANSACCIONALES (63 TABLAS)
-- ============================================================================

IF OBJECT_ID('[catalogo].[Categorias]', 'U') IS NULL
BEGIN
    CREATE TABLE [catalogo].[Categorias] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [Descripcion] VARCHAR(200) NULL,
    CONSTRAINT [PK__Categori__3214EC27E087667B] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Categori__75E3EFCF14FB85CD] UNIQUE ([Nombre])
    );
END
GO
IF OBJECT_ID('[catalogo].[Ingredientes]', 'U') IS NULL
BEGIN
    CREATE TABLE [catalogo].[Ingredientes] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [PrecioAdicional] DECIMAL(10,2) DEFAULT ((0.00)) NOT NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__Ingredie__3214EC27F291078D] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[catalogo].[Productos]', 'U') IS NULL
BEGIN
    CREATE TABLE [catalogo].[Productos] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [CategoriaID] INT NOT NULL,
    [PrecioBase] DECIMAL(10,2) NOT NULL,
    [EsFicticio] BIT DEFAULT ((0)) NOT NULL,
    [PorcentajeDescuento] DECIMAL(5,2) DEFAULT ((0.00)) NOT NULL,
    [ImagenUrl] VARCHAR(255) NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    [CreadoEn] DATETIME DEFAULT (getdate()) NOT NULL,
    [TasaIVA] DECIMAL(5,2) NULL,
    [MotivoExencion] NVARCHAR(200) NULL,
    CONSTRAINT [PK__Producto__3214EC2717EB731C] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[catalogo].[UnidadesMedida]', 'U') IS NULL
BEGIN
    CREATE TABLE [catalogo].[UnidadesMedida] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [Abreviatura] VARCHAR(10) NOT NULL,
    CONSTRAINT [PK__Unidades__3214EC271FA3E725] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Unidades__75E3EFCFD396AAE3] UNIQUE ([Nombre])
    );
END
GO
IF OBJECT_ID('[contabilidad].[AsientosDiario]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[AsientosDiario] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [PeriodoID] INT NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    [Descripcion] VARCHAR(255) NOT NULL,
    [ReferenciaExterna] VARCHAR(50) NULL,
    [TipoDocumento] VARCHAR(50) NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Contabilizado') NOT NULL,
    [UsuarioID] INT NOT NULL,
    [FechaCreacion] DATETIME DEFAULT (getdate()) NOT NULL,
    [TipoComprobanteID] INT NULL,
    [NumeroComprobante] VARCHAR(20) NULL,
    [IP] VARCHAR(45) NULL,
    [AnuladoPor] INT NULL,
    [FechaAnulacion] DATETIME NULL,
    [MotivoAnulacion] VARCHAR(255) NULL,
    [EmisorJSON] NVARCHAR(MAX) NULL,
    CONSTRAINT [PK__Asientos__3214EC273124490D] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Asiento_Estado] CHECK ([Estado]='Anulado' OR [Estado]='Contabilizado' OR [Estado]='Borrador')
    );
END
GO
IF OBJECT_ID('[contabilidad].[CatalogoCuentas]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[CatalogoCuentas] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Codigo] VARCHAR(20) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [Clase] VARCHAR(20) NOT NULL,
    [Grupo] VARCHAR(50) NOT NULL,
    [Naturaleza] VARCHAR(10) NOT NULL,
    [Activa] BIT DEFAULT ((1)) NOT NULL,
    [Nivel] TINYINT DEFAULT ((4)) NOT NULL,
    [CuentaPadreID] INT NULL,
    [EsTransaccional] BIT DEFAULT ((1)) NOT NULL,
    [Descripcion] VARCHAR(255) NULL,
    [OrdenVisualizacion] INT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__Catalogo__3214EC27240F3D1E] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Cuenta_Clase] CHECK ([Clase]='Gasto' OR [Clase]='Costo' OR [Clase]='Ingreso' OR [Clase]='Capital' OR [Clase]='Pasivo' OR [Clase]='Activo'),
    CONSTRAINT [CK_Cuenta_Naturaleza] CHECK ([Naturaleza]='Acreedora' OR [Naturaleza]='Deudora'),
    CONSTRAINT [UQ__Catalogo__06370DAC3EAC1E28] UNIQUE ([Codigo])
    );
END
GO
IF OBJECT_ID('[contabilidad].[ConciliacionBancaria]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[ConciliacionBancaria] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [PeriodoID] INT NOT NULL,
    [FechaConciliacion] DATETIME DEFAULT (getdate()) NOT NULL,
    [SaldoSegunBanco] DECIMAL(18,2) NOT NULL,
    [SaldoSegunLibros] DECIMAL(18,2) NOT NULL,
    [Diferencia] AS ([SaldoSegunBanco]-[SaldoSegunLibros]) PERSISTED,
    [Estado] VARCHAR(20) DEFAULT ('Borrador') NOT NULL,
    [RealizadoPor] INT NOT NULL,
    CONSTRAINT [PK__Concilia__3214EC2701F3C498] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Conc_Estado] CHECK ([Estado]='Conciliado' OR [Estado]='Borrador')
    );
END
GO
IF OBJECT_ID('[contabilidad].[CuentasPorCobrar]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[CuentasPorCobrar] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ClienteID] INT NOT NULL,
    [FacturaID] INT NOT NULL,
    [MontoOriginal] DECIMAL(18,2) NOT NULL,
    [MontoPagado] DECIMAL(18,2) DEFAULT ((0)) NOT NULL,
    [SaldoPendiente] AS ([MontoOriginal]-[MontoPagado]) PERSISTED,
    [FechaEmision] DATETIME DEFAULT (getdate()) NOT NULL,
    [FechaVencimiento] DATETIME NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Vigente') NOT NULL,
    CONSTRAINT [PK__CuentasP__3214EC273CED7A6C] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_CxC_Estado] CHECK ([Estado]='Incobrable' OR [Estado]='Pagada' OR [Estado]='Vencida' OR [Estado]='Vigente')
    );
END
GO
IF OBJECT_ID('[contabilidad].[CuentasPorPagar]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[CuentasPorPagar] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ProveedorID] INT NOT NULL,
    [CompraID] INT NULL,
    [MontoOriginal] DECIMAL(18,2) NOT NULL,
    [MontoPagado] DECIMAL(18,2) DEFAULT ((0)) NOT NULL,
    [SaldoPendiente] AS ([MontoOriginal]-[MontoPagado]) PERSISTED,
    [FechaEmision] DATETIME DEFAULT (getdate()) NOT NULL,
    [FechaVencimiento] DATETIME NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Vigente') NOT NULL,
    CONSTRAINT [PK__CuentasP__3214EC2798B0D81B] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_CxP_Estado] CHECK ([Estado]='Pagada' OR [Estado]='Vencida' OR [Estado]='Vigente')
    );
END
GO
IF OBJECT_ID('[contabilidad].[DetalleAsientos]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[DetalleAsientos] (
    [ID] BIGINT IDENTITY(1,1) NOT NULL,
    [AsientoID] INT NOT NULL,
    [CuentaID] INT NOT NULL,
    [Debe] DECIMAL(18,4) DEFAULT ((0.0000)) NOT NULL,
    [Haber] DECIMAL(18,4) DEFAULT ((0.0000)) NOT NULL,
    [Descripcion] VARCHAR(255) NULL,
    [DocumentoRelacionado] VARCHAR(50) NULL,
    CONSTRAINT [PK__DetalleA__3214EC27531E64DD] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Detalle_Montos] CHECK ([Debe]>=(0) AND [Haber]>=(0) AND ([Debe]>(0) OR [Haber]>(0)))
    );
END
GO
IF OBJECT_ID('[contabilidad].[DetalleConciliacion]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[DetalleConciliacion] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ConciliacionID] INT NOT NULL,
    [Tipo] VARCHAR(30) NOT NULL,
    [Descripcion] VARCHAR(255) NOT NULL,
    [Monto] DECIMAL(18,2) NOT NULL,
    [FechaDocumento] DATE NULL,
    CONSTRAINT [PK__DetalleC__3214EC2725B8903F] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[contabilidad].[EgresosPrivados]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[EgresosPrivados] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Concepto] VARCHAR(200) NOT NULL,
    [Monto] DECIMAL(10,2) NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    [UsuarioID] INT NOT NULL,
    CONSTRAINT [PK__EgresosP__3214EC27DCA43DD5] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[contabilidad].[PagosCxC]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[PagosCxC] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [CuentaPorCobrarID] INT NOT NULL,
    [AsientoID] INT NOT NULL,
    [MontoPagado] DECIMAL(18,2) NOT NULL,
    [FechaPago] DATETIME DEFAULT (getdate()) NOT NULL,
    [MetodoPago] VARCHAR(20) NOT NULL,
    CONSTRAINT [PK__PagosCxC__3214EC2780405D67] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[contabilidad].[PeriodosContables]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[PeriodosContables] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Mes] INT NOT NULL,
    [Anio] INT NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Abierto') NOT NULL,
    [FechaApertura] DATETIME DEFAULT (getdate()) NOT NULL,
    [FechaCierre] DATETIME NULL,
    [CerradoPor] INT NULL,
    [CierreUtilidad] DECIMAL(18,4) NULL,
    [CierreReservaLegal] DECIMAL(18,4) NULL,
    [CerradoEn] DATETIME NULL,
    CONSTRAINT [PK__Periodos__3214EC274135BDAB] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Periodo_Estado] CHECK ([Estado]='Cerrado' OR [Estado]='Abierto'),
    CONSTRAINT [CK_Periodo_Mes] CHECK ([Mes]>=(1) AND [Mes]<=(12)),
    CONSTRAINT [UQ_Periodo] UNIQUE ([Mes], [Anio])
    );
END
GO
IF OBJECT_ID('[contabilidad].[TiposComprobante]', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[TiposComprobante] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Codigo] VARCHAR(5) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [CorrelativoActual] INT DEFAULT ((0)) NOT NULL,
    [Prefijo] VARCHAR(10) NOT NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__TiposCom__3214EC2774F5FDDF] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__TiposCom__06370DAC401F92C3] UNIQUE ([Codigo])
    );
END
GO
IF OBJECT_ID('[crm].[Clientes]', 'U') IS NULL
BEGIN
    CREATE TABLE [crm].[Clientes] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [Telefono] VARCHAR(20) NULL,
    [NivelConfianzaID] INT NOT NULL,
    [TotalCompras] INT DEFAULT ((0)) NOT NULL,
    [CreadoEn] DATETIME DEFAULT (getdate()) NOT NULL,
    [Apellidos] VARCHAR(100) NULL,
    [PasswordHash] VARCHAR(255) NULL,
    [EsInvitado] BIT DEFAULT ((1)) NOT NULL,
    [Genero] VARCHAR(20) NULL,
    [FechaNacimiento] DATE NULL,
    [RutaFotoPerfil] VARCHAR(255) NULL,
    CONSTRAINT [PK__Clientes__3214EC2713AB51E7] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[crm].[Cotizaciones]', 'U') IS NULL
BEGIN
    CREATE TABLE [crm].[Cotizaciones] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ClienteID] INT NULL,
    [SessionID] VARCHAR(50) NULL,
    [Especificaciones] VARCHAR(MAX) NOT NULL,
    [FechaEntrega] DATETIME NOT NULL,
    [RutaImagenReferencia] VARCHAR(255) NULL,
    [TelefonoContacto] VARCHAR(20) NULL,
    [PrecioCotizado] DECIMAL(10,2) NULL,
    [Estado] VARCHAR(20) DEFAULT ('Pendiente') NOT NULL,
    [FechaSolicitud] DATETIME DEFAULT (getdate()) NOT NULL,
    [NombreContacto] VARCHAR(150) NULL,
    CONSTRAINT [PK__Cotizaci__3214EC27FA39CFF6] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[crm].[NivelesConfianza]', 'U') IS NULL
BEGIN
    CREATE TABLE [crm].[NivelesConfianza] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [ComprasMinimas] INT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__NivelesC__3214EC2706F2F973] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__NivelesC__75E3EFCFB376A8FD] UNIQUE ([Nombre])
    );
END
GO
IF OBJECT_ID('[fiscal].[BitacoraFiscal]', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[BitacoraFiscal] (
    [ID] BIGINT IDENTITY(1,1) NOT NULL,
    [Fecha] DATETIME2(7) DEFAULT (sysdatetime()) NOT NULL,
    [UsuarioID] INT NULL,
    [Accion] NVARCHAR(50) NOT NULL,
    [Entidad] NVARCHAR(50) NOT NULL,
    [EntidadID] INT NULL,
    [Detalle] NVARCHAR(MAX) NOT NULL,
    [IP] VARCHAR(45) NULL,
    CONSTRAINT [PK__Bitacora__3214EC275C4AC515] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[fiscal].[DGI_Exportaciones]', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Exportaciones] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [RevisionID] INT NOT NULL,
    [Nombre] NVARCHAR(150) NOT NULL,
    [SHA256] CHAR(64) NOT NULL,
    [Archivo] VARBINARY NOT NULL,
    [UsuarioID] INT NOT NULL,
    [Fecha] DATETIME2(7) DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [PK__DGI_Expo__3214EC27C587E16E] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[fiscal].[DGI_Observaciones]', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Observaciones] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [RevisionID] INT NOT NULL,
    [Hallazgo] CHAR(24) NOT NULL,
    [Comentario] NVARCHAR(1000) NOT NULL,
    [UsuarioID] INT NOT NULL,
    [Fecha] DATETIME2(7) DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [PK__DGI_Obse__3214EC278971C835] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[fiscal].[DGI_Periodos]', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Periodos] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Desde] DATE NOT NULL,
    [Hasta] DATE NOT NULL,
    [Estado] VARCHAR(12) DEFAULT ('Abierto') NOT NULL,
    [CreadoPor] INT NOT NULL,
    [CreadoEn] DATETIME2(7) DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [PK__DGI_Peri__3214EC27FBD91B0E] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_DGI_PeriodoFechas] CHECK ([Hasta]>=[Desde]),
    CONSTRAINT [CK_DGI_PeriodoEstado] CHECK ([Estado]='Cerrado' OR [Estado]='Abierto'),
    CONSTRAINT [UX_DGI_Periodo] UNIQUE ([Desde], [Hasta])
    );
END
GO
IF OBJECT_ID('[fiscal].[DGI_Revisiones]', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Revisiones] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [PeriodoID] INT NOT NULL,
    [Obligacion] NVARCHAR(200) NOT NULL,
    [Version] INT NOT NULL,
    [Motor] VARCHAR(30) NOT NULL,
    [Huella] CHAR(64) NOT NULL,
    [SnapshotJSON] NVARCHAR(MAX) NOT NULL,
    [ResultadoJSON] NVARCHAR(MAX) NOT NULL,
    [Estado] VARCHAR(15) DEFAULT ('BORRADOR') NOT NULL,
    [CreadoPor] INT NOT NULL,
    [CreadoEn] DATETIME2(7) DEFAULT (sysutcdatetime()) NOT NULL,
    [RevisadoPor] INT NULL,
    [RevisadoEn] DATETIME2(7) NULL,
    [NotaRevision] NVARCHAR(1000) NULL,
    [AprobadoPor] INT NULL,
    [AprobadoEn] DATETIME2(7) NULL,
    CONSTRAINT [PK__DGI_Revi__3214EC271F693ABD] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_DGI_RevisionEstado] CHECK ([Estado]='OBSOLETO' OR [Estado]='EXPORTADO' OR [Estado]='APROBADO' OR [Estado]='EN_REVISION' OR [Estado]='BORRADOR'),
    CONSTRAINT [UX_DGI_Revision] UNIQUE ([PeriodoID], [Obligacion], [Version])
    );
END
GO
IF OBJECT_ID('[produccion].[ComprasMateriaPrima]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[ComprasMateriaPrima] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [MateriaPrimaID] INT NOT NULL,
    [ProveedorID] INT NOT NULL,
    [Cantidad] DECIMAL(10,2) NOT NULL,
    [CostoTotal] DECIMAL(10,2) NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    [FacturaProveedor] NVARCHAR(50) NULL,
    [IVADocumentado] DECIMAL(18,2) DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__ComprasM__3214EC272FC26958] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[produccion].[ConsumoLote]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[ConsumoLote] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [LoteID] INT NOT NULL,
    [MateriaPrimaID] INT NOT NULL,
    [CantidadUsada] DECIMAL(10,2) NOT NULL,
    CONSTRAINT [PK__ConsumoL__3214EC274068132E] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[produccion].[MateriaPrima]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[MateriaPrima] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [UnidadMedidaID] INT NOT NULL,
    [StockActual] DECIMAL(10,2) DEFAULT ((0.00)) NOT NULL,
    [StockMinimo] DECIMAL(10,2) DEFAULT ((0.00)) NOT NULL,
    CONSTRAINT [PK__MateriaP__3214EC27A0349599] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_MateriaPrima_Stock] CHECK ([StockActual]>=(0))
    );
END
GO
IF OBJECT_ID('[produccion].[Mermas]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[Mermas] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ProductoID] INT NOT NULL,
    [Cantidad] INT NOT NULL,
    [Motivo] VARCHAR(50) NOT NULL,
    [Observaciones] VARCHAR(200) NULL,
    [UsuarioID] INT NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    CONSTRAINT [PK__Mermas__3214EC27816CAA35] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Mermas_Motivo] CHECK ([Motivo]='Otro' OR [Motivo]='Vencido' OR [Motivo]='Merma Horneado' OR [Motivo]='Defectuoso' OR [Motivo]='Pan Frio')
    );
END
GO
IF OBJECT_ID('[produccion].[ProduccionLotes]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[ProduccionLotes] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ProductoID] INT NOT NULL,
    [CantidadProducida] INT NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    [CantidadEsperada] INT NULL,
    CONSTRAINT [PK__Producci__3214EC2719BAD7C4] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[produccion].[Proveedores]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[Proveedores] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(100) NOT NULL,
    [Telefono] VARCHAR(20) NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__Proveedo__3214EC27ACE128A0] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[produccion].[RecetaProducto]', 'U') IS NULL
BEGIN
    CREATE TABLE [produccion].[RecetaProducto] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ProductoID] INT NOT NULL,
    [MateriaPrimaID] INT NOT NULL,
    [CantidadNecesaria] DECIMAL(10,2) NOT NULL,
    CONSTRAINT [PK__RecetaPr__3214EC2788A7B071] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[rrhh].[Asistencia]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[Asistencia] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [TurnoID] INT NOT NULL,
    [Fecha] DATE NOT NULL,
    [HoraEntrada] TIME(7) NULL,
    [HoraSalida] TIME(7) NULL,
    [EstadoEntrada] VARCHAR(20) NULL,
    [Observaciones] VARCHAR(200) NULL,
    [RegistradoPor] INT NULL,
    [FechaRegistro] DATETIME DEFAULT (getdate()) NOT NULL,
    CONSTRAINT [PK__Asistenc__3214EC2757C1525D] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Asistencia_Estado] CHECK ([EstadoEntrada]='Ausente' OR [EstadoEntrada]='Llegada Tardia' OR [EstadoEntrada]='A Tiempo')
    );
END
GO
IF OBJECT_ID('[rrhh].[DeduccionesJudiciales]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[DeduccionesJudiciales] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [TipoDeduccion] VARCHAR(30) NOT NULL,
    [Beneficiario] VARCHAR(150) NOT NULL,
    [PorcentajeSalarioNeto] DECIMAL(5,2) NOT NULL,
    [MontoFijo] DECIMAL(10,2) NULL,
    [NumeroJuzgado] VARCHAR(50) NULL,
    [FechaInicio] DATE NOT NULL,
    [FechaFin] DATE NULL,
    [Activa] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__Deduccio__3214EC2749B16450] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_DeduccionesJudiciales_Tipo] CHECK ([TipoDeduccion]='Embargo Comercial' OR [TipoDeduccion]='Pension Alimenticia')
    );
END
GO
IF OBJECT_ID('[rrhh].[DetalleNomina]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[DetalleNomina] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [NominaID] INT NOT NULL,
    [Concepto] VARCHAR(100) NOT NULL,
    [Tipo] VARCHAR(10) NOT NULL,
    [Monto] DECIMAL(10,2) NOT NULL,
    [Descripcion] VARCHAR(200) NULL,
    CONSTRAINT [PK__DetalleN__3214EC27AD42A8C6] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_DetalleNomina_Tipo] CHECK ([Tipo]='Patronal' OR [Tipo]='Deduccion' OR [Tipo]='Ingreso')
    );
END
GO
IF OBJECT_ID('[rrhh].[Empleados]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[Empleados] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [UsuarioID] INT NULL,
    [NombreCompleto] VARCHAR(150) NOT NULL,
    [Cedula] VARCHAR(20) NOT NULL,
    [FechaNacimiento] DATE NULL,
    [Genero] VARCHAR(10) NULL,
    [Direccion] VARCHAR(300) NULL,
    [Telefono] VARCHAR(20) NULL,
    [CorreoElectronico] VARCHAR(100) NULL,
    [NumeroINSS] VARCHAR(20) NULL,
    [Cargo] VARCHAR(100) NOT NULL,
    [FechaIngreso] DATE NOT NULL,
    [FechaEgreso] DATE NULL,
    [TipoContrato] VARCHAR(30) DEFAULT ('Indefinido') NOT NULL,
    [TipoJornada] VARCHAR(20) DEFAULT ('Diurna') NOT NULL,
    [SalarioBase] DECIMAL(10,2) NOT NULL,
    [FormaPago] VARCHAR(20) DEFAULT ('Mensual') NOT NULL,
    [EstadoEmpleado] VARCHAR(20) DEFAULT ('Activo') NOT NULL,
    [MotivoEgreso] VARCHAR(100) NULL,
    [ConsentimientoDatos] BIT DEFAULT ((0)) NOT NULL,
    [FechaConsentimiento] DATETIME NULL,
    [CreadoEn] DATETIME DEFAULT (getdate()) NOT NULL,
    [FechaFinContrato] DATE NULL,
    [FotoPerfil] VARCHAR(255) NULL,
    [HoraEntrada] TIME(7) NULL,
    [HoraSalida] TIME(7) NULL,
    [FaceDescriptor] VARCHAR(MAX) NULL,
    CONSTRAINT [PK__Empleado__3214EC271BAB02E6] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Empleados_Contrato] CHECK ([TipoContrato]='Por Obra' OR [TipoContrato]='Determinado' OR [TipoContrato]='Indefinido'),
    CONSTRAINT [CK_Empleados_Estado] CHECK ([EstadoEmpleado]='Liquidado' OR [EstadoEmpleado]='Suspendido' OR [EstadoEmpleado]='Licencia' OR [EstadoEmpleado]='Subsidio' OR [EstadoEmpleado]='Activo'),
    CONSTRAINT [CK_Empleados_FormaPago] CHECK ([FormaPago]='Mensual' OR [FormaPago]='Quincenal' OR [FormaPago]='Catorcenal' OR [FormaPago]='Semanal'),
    CONSTRAINT [CK_Empleados_Jornada] CHECK ([TipoJornada]='Mixta' OR [TipoJornada]='Nocturna' OR [TipoJornada]='Diurna'),
    CONSTRAINT [UQ__Empleado__B4ADFE382328CC32] UNIQUE ([Cedula])
    );
END
GO
IF OBJECT_ID('[rrhh].[FeriadosNacionales]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[FeriadosNacionales] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Fecha] DATE NOT NULL,
    [Descripcion] VARCHAR(100) NOT NULL,
    [Anio] INT NOT NULL,
    [EsMovil] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__Feriados__3214EC27D592150A] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[rrhh].[IncidentesLaborales]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[IncidentesLaborales] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [TipoIncidente] VARCHAR(30) NOT NULL,
    [Gravedad] VARCHAR(20) NOT NULL,
    [Descripcion] VARCHAR(MAX) NOT NULL,
    [FechaIncidente] DATETIME NOT NULL,
    [FechaReporte] DATETIME DEFAULT (getdate()) NOT NULL,
    [NotificadoMITRAB] BIT DEFAULT ((0)) NOT NULL,
    [FechaNotificacionMITRAB] DATETIME NULL,
    [AccionesCorrectivas] VARCHAR(MAX) NULL,
    [RegistradoPor] INT NOT NULL,
    CONSTRAINT [PK__Incident__3214EC27F43D3F30] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Incidentes_Gravedad] CHECK ([Gravedad]='Mortal' OR [Gravedad]='Muy Grave' OR [Gravedad]='Grave' OR [Gravedad]='Leve'),
    CONSTRAINT [CK_Incidentes_Tipo] CHECK ([TipoIncidente]='Enfermedad Ocupacional' OR [TipoIncidente]='Casi Accidente' OR [TipoIncidente]='Accidente')
    );
END
GO
IF OBJECT_ID('[rrhh].[LicenciasEmpleados]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[LicenciasEmpleados] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [TipoLicencia] VARCHAR(50) NOT NULL,
    [FechaInicio] DATE NOT NULL,
    [FechaFin] DATE NOT NULL,
    [DiasOtorgados] INT NOT NULL,
    [PagoEmpleador] DECIMAL(5,2) DEFAULT ((100.00)) NOT NULL,
    [PagoINSS] DECIMAL(5,2) DEFAULT ((0.00)) NOT NULL,
    [Observaciones] VARCHAR(300) NULL,
    [AprobadoPor] INT NULL,
    [FechaRegistro] DATETIME DEFAULT (getdate()) NOT NULL,
    CONSTRAINT [PK__Licencia__3214EC275D65DAB6] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Licencias_Tipo] CHECK ([TipoLicencia]='Otro' OR [TipoLicencia]='Permiso Personal' OR [TipoLicencia]='Riesgo Profesional' OR [TipoLicencia]='Luto' OR [TipoLicencia]='Matrimonio' OR [TipoLicencia]='Paternidad' OR [TipoLicencia]='Maternidad' OR [TipoLicencia]='Enfermedad Comun' OR [TipoLicencia]='Vacaciones')
    );
END
GO
IF OBJECT_ID('[rrhh].[Nomina]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[Nomina] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [PeriodoInicio] DATE NOT NULL,
    [PeriodoFin] DATE NOT NULL,
    [SalarioBruto] DECIMAL(10,2) NOT NULL,
    [HorasExtras] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [MontoHorasExtras] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [OtrosIngresos] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [TotalDevengado] DECIMAL(10,2) NOT NULL,
    [INSSLaboral] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [IRMensual] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [PensionAlimenticia] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [ValesDescontados] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [OtrasDeducciones] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [TotalDeducciones] DECIMAL(10,2) NOT NULL,
    [SalarioNeto] DECIMAL(10,2) NOT NULL,
    [INSSPatronal] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [INATEC] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Borrador') NOT NULL,
    [FechaGeneracion] DATETIME DEFAULT (getdate()) NOT NULL,
    [GeneradoPor] INT NULL,
    CONSTRAINT [PK__Nomina__3214EC275966D0CF] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Nomina_Estado] CHECK ([Estado]='Contabilizada' OR [Estado]='Anulada' OR [Estado]='Pagada' OR [Estado]='Aprobada' OR [Estado]='Borrador')
    );
END
GO
IF OBJECT_ID('[rrhh].[PerfilesPuesto]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[PerfilesPuesto] (
    [Cargo] NVARCHAR(100) NOT NULL,
    [PerfilPuesto] NVARCHAR(1000) DEFAULT (N'') NOT NULL,
    [Obligaciones] NVARCHAR(2000) DEFAULT (N'') NOT NULL,
    [RequisitosCompetencias] NVARCHAR(1000) DEFAULT (N'') NOT NULL,
    [ActualizadoEn] DATETIME2(7) DEFAULT (sysutcdatetime()) NOT NULL,
    [ActualizadoPor] INT NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__Perfiles__68A1C0DE85EB3BEC] PRIMARY KEY ([Cargo])
    );
END
GO
IF OBJECT_ID('[rrhh].[TurnosLaborales]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[TurnosLaborales] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [HoraEntrada] TIME(7) NOT NULL,
    [HoraSalida] TIME(7) NOT NULL,
    [ToleranciaMinutos] INT DEFAULT ((15)) NOT NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    CONSTRAINT [PK__TurnosLa__3214EC278F53B07F] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[rrhh].[ValesEmpleados]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[ValesEmpleados] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [EmpleadoID] INT NOT NULL,
    [Monto] DECIMAL(10,2) NOT NULL,
    [Fecha] DATETIME DEFAULT (getdate()) NOT NULL,
    [Descontado] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__ValesEmp__3214EC27957F04F4] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[rrhh].[escala_salarial]', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[escala_salarial] (
    [id] INT IDENTITY(1,1) NOT NULL,
    [nivel] VARCHAR(10) NOT NULL,
    [cargo] VARCHAR(100) NOT NULL,
    [limite_inferior] INT NULL,
    [limite_superior] INT NOT NULL,
    [salario_base] DECIMAL(12,2) NOT NULL,
    CONSTRAINT [PK__escala_s__3213E83F14177CED] PRIMARY KEY ([id])
    );
END
GO
IF OBJECT_ID('[seguridad].[AlertasSMTPDedup]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[AlertasSMTPDedup] (
    [DedupKey] BINARY NOT NULL,
    [UltimoEnvio] DATETIME2(3) NULL,
    [ClaimToken] UNIQUEIDENTIFIER NULL,
    [LeaseHasta] DATETIME2(3) NULL,
    CONSTRAINT [PK_AlertasSMTPDedup] PRIMARY KEY ([DedupKey])
    );
END
GO
IF OBJECT_ID('[seguridad].[AlertasSMTPOutbox]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[AlertasSMTPOutbox] (
    [ErrorID] BIGINT NOT NULL,
    [DedupKey] BINARY NOT NULL,
    [Estado] VARCHAR(12) DEFAULT ('Pending') NOT NULL,
    [DisponibleDesde] DATETIME2(3) DEFAULT (sysutcdatetime()) NOT NULL,
    [ClaimToken] UNIQUEIDENTIFIER NULL,
    [LeaseHasta] DATETIME2(3) NULL,
    [Intentos] INT DEFAULT ((0)) NOT NULL,
    [DestinatariosJSON] NVARCHAR(MAX) NULL,
    [Forzar] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK_AlertasSMTPOutbox] PRIMARY KEY ([ErrorID]),
    CONSTRAINT [CK_AlertasSMTP_Estado] CHECK ([Estado]='Suppressed' OR [Estado]='Sent' OR [Estado]='Sending' OR [Estado]='Pending'),
    CONSTRAINT [CK_AlertasSMTP_JSON] CHECK ([DestinatariosJSON] IS NULL OR isjson([DestinatariosJSON])=(1))
    );
END
GO
IF OBJECT_ID('[seguridad].[AuditLog]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[AuditLog] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [UsuarioID] INT NULL,
    [Accion] VARCHAR(100) NOT NULL,
    [Entidad] VARCHAR(50) NOT NULL,
    [EntidadID] INT NULL,
    [DatosAntes] VARCHAR(MAX) NULL,
    [DatosDespues] VARCHAR(MAX) NULL,
    [IP] VARCHAR(45) NULL,
    [FechaHora] DATETIME DEFAULT (getdate()) NOT NULL,
    CONSTRAINT [PK__AuditLog__3214EC2745AE9851] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[seguridad].[AuthChallenges]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[AuthChallenges] (
    [Token] VARCHAR(64) NOT NULL,
    [Kind] VARCHAR(20) NOT NULL,
    [Subject] VARCHAR(32) NOT NULL,
    [Verifier] VARCHAR(64) DEFAULT ('') NOT NULL,
    [Secret] VARCHAR(64) DEFAULT ('') NOT NULL,
    [Binding] VARCHAR(64) DEFAULT ('') NOT NULL,
    [ExpiresAt] BIGINT NOT NULL,
    [Attempts] INT DEFAULT ((0)) NOT NULL,
    [Verified] BIT DEFAULT ((0)) NOT NULL,
    [Consumed] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__AuthChal__1EB4F816AAC881DA] PRIMARY KEY ([Token]),
    CONSTRAINT [CK_AuthChallenges_Kind] CHECK ([Kind]='totp_login' OR [Kind]='totp_enroll' OR [Kind]='sms'),
    CONSTRAINT [CK_AuthChallenges_Attempts] CHECK ([Attempts]>=(0))
    );
END
GO
IF OBJECT_ID('[seguridad].[BitacoraErrores]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[BitacoraErrores] (
    [ID] BIGINT IDENTITY(1,1) NOT NULL,
    [FechaHora] DATETIME2(7) DEFAULT (sysdatetime()) NOT NULL,
    [Origen] VARCHAR(30) DEFAULT ('SQL_SP') NOT NULL,
    [Severidad] VARCHAR(15) DEFAULT ('ERROR') NOT NULL,
    [NumeroError] INT NULL,
    [EstadoError] INT NULL,
    [LineaError] INT NULL,
    [Procedimiento] NVARCHAR(128) NULL,
    [EsquemaOrigen] NVARCHAR(64) NULL,
    [MensajeError] NVARCHAR(2000) NOT NULL,
    [DetalleTecnico] NVARCHAR(MAX) NULL,
    [ParametrosJSON] NVARCHAR(MAX) NULL,
    [UsuarioID] INT NULL,
    [Username] NVARCHAR(100) NULL,
    [RolAplicacion] NVARCHAR(50) NULL,
    [UsuarioBD] NVARCHAR(128) DEFAULT (original_login()) NOT NULL,
    [DireccionIP] VARCHAR(45) NULL,
    [RutaHTTP] NVARCHAR(255) NULL,
    [NotificadoSMTP] BIT DEFAULT ((0)) NOT NULL,
    [FechaNotificacion] DATETIME2(7) NULL,
    CONSTRAINT [PK__Bitacora__3214EC274CBA191B] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_BitacoraErrores_Severidad] CHECK ([Severidad]='CRITICAL' OR [Severidad]='ERROR' OR [Severidad]='WARNING' OR [Severidad]='INFO')
    );
END
GO
IF OBJECT_ID('[seguridad].[BloqueosCuenta]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[BloqueosCuenta] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Identificador] NVARCHAR(100) NOT NULL,
    [DireccionIP] VARCHAR(45) NOT NULL,
    [IntentosFallidos] INT DEFAULT ((1)) NOT NULL,
    [PrimerIntento] DATETIME2(7) DEFAULT (sysdatetime()) NOT NULL,
    [UltimoIntento] DATETIME2(7) DEFAULT (sysdatetime()) NOT NULL,
    [BloqueadoHasta] DATETIME2(7) NULL,
    [Motivo] NVARCHAR(255) NULL,
    CONSTRAINT [PK__Bloqueos__3214EC27D26F49DB] PRIMARY KEY ([ID]),
    CONSTRAINT [UX_BloqueosCuenta_Identificador_IP] UNIQUE ([Identificador], [DireccionIP])
    );
END
GO
IF OBJECT_ID('[seguridad].[ConfiguracionSistema]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[ConfiguracionSistema] (
    [Clave] VARCHAR(50) NOT NULL,
    [Valor] NVARCHAR(MAX) NOT NULL,
    [Descripcion] VARCHAR(200) NULL,
    CONSTRAINT [PK__Configur__E8181E10348534E0] PRIMARY KEY ([Clave])
    );
END
GO
IF OBJECT_ID('[seguridad].[Roles]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[Roles] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Nombre] VARCHAR(50) NOT NULL,
    [Descripcion] VARCHAR(200) NULL,
    CONSTRAINT [PK__Roles__3214EC2769237CBC] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Roles__75E3EFCFDDB9B64E] UNIQUE ([Nombre])
    );
END
GO
IF OBJECT_ID('[seguridad].[Usuarios]', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[Usuarios] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [NombreCompleto] VARCHAR(100) NOT NULL,
    [Username] VARCHAR(50) NOT NULL,
    [PasswordHash] VARCHAR(255) NOT NULL,
    [RolID] INT NOT NULL,
    [Activo] BIT DEFAULT ((1)) NOT NULL,
    [CreadoEn] DATETIME DEFAULT (getdate()) NOT NULL,
    [TOTPSecret] VARCHAR(32) NULL,
    [TOTPEnabled] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__Usuarios__3214EC27DAFC2D86] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Usuarios__536C85E42D714276] UNIQUE ([Username])
    );
END
GO
IF OBJECT_ID('[ventas].[ArqueoAuditLog]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[ArqueoAuditLog] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ArqueoID] INT NOT NULL,
    [UsuarioID] INT NOT NULL,
    [Accion] VARCHAR(50) NOT NULL,
    [Detalle] VARCHAR(500) NULL,
    [FechaAccion] DATETIME DEFAULT (getdate()) NOT NULL,
    [DireccionIP] VARCHAR(45) NULL,
    CONSTRAINT [PK__ArqueoAu__3214EC27958C7CBB] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[ventas].[ArqueoCaja]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[ArqueoCaja] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [TurnoID] INT NOT NULL,
    [UsuarioID] INT NOT NULL,
    [EfectivoContado] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [TransferenciasContadas] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [DolaresContados] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [TipoCambioUsado] DECIMAL(10,4) NULL,
    [EfectivoSistema] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [TransferenciasSistema] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [DiferenciaEfectivo] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [DiferenciaTransferencias] DECIMAL(10,2) DEFAULT ((0)) NOT NULL,
    [Observaciones] VARCHAR(500) NULL,
    [FechaArqueo] DATETIME DEFAULT (getdate()) NOT NULL,
    [VerificadoPorID] INT NULL,
    [FechaVerificacion] DATETIME NULL,
    [EstadoArqueo] VARCHAR(20) DEFAULT ('Pendiente') NOT NULL,
    [NotasDiscrepancia] VARCHAR(1000) NULL,
    [RequiereJustificacion] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__ArqueoCa__3214EC27B36C5077] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_ArqueoCaja_Estado] CHECK ([EstadoArqueo]='Cerrado' OR [EstadoArqueo]='Verificado' OR [EstadoArqueo]='Pendiente')
    );
END
GO
IF OBJECT_ID('[ventas].[ArqueoDetalleDenominacion]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[ArqueoDetalleDenominacion] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [ArqueoID] INT NOT NULL,
    [TipoMoneda] VARCHAR(10) NOT NULL,
    [Denominacion] DECIMAL(10,2) NOT NULL,
    [Cantidad] INT DEFAULT ((0)) NOT NULL,
    [Subtotal] AS ([Denominacion]*[Cantidad]) PERSISTED,
    CONSTRAINT [PK__ArqueoDe__3214EC278A46E0DD] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[ventas].[DetalleFacturas]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[DetalleFacturas] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [FacturaID] INT NOT NULL,
    [ProductoID] INT NOT NULL,
    [Cantidad] INT NOT NULL,
    [PrecioUnitario] DECIMAL(10,2) NOT NULL,
    [Subtotal] DECIMAL(10,2) NOT NULL,
    CONSTRAINT [PK__DetalleF__3214EC272A796703] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[ventas].[DetalleIngredientes]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[DetalleIngredientes] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [DetalleFacturaID] INT NOT NULL,
    [IngredienteID] INT NOT NULL,
    [PrecioAplicado] DECIMAL(10,2) NOT NULL,
    CONSTRAINT [PK__DetalleI__3214EC27CA52F1B2] PRIMARY KEY ([ID])
    );
END
GO
IF OBJECT_ID('[ventas].[Encargos]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[Encargos] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [FacturaID] INT NOT NULL,
    [FechaEntrega] DATETIME NOT NULL,
    [Estado] VARCHAR(20) DEFAULT ('Pendiente') NOT NULL,
    [PoliticasAceptadas] BIT DEFAULT ((1)) NOT NULL,
    [NotasCliente] VARCHAR(500) NULL,
    [Especificaciones] VARCHAR(MAX) NULL,
    [RutaImagenReferencia] VARCHAR(255) NULL,
    [TelefonoContacto] VARCHAR(20) NULL,
    CONSTRAINT [PK__Encargos__3214EC2728CAC0F7] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Encargos_Estado] CHECK ([Estado]='Entregado' OR [Estado]='Listo' OR [Estado]='En Proceso' OR [Estado]='Pendiente')
    );
END
GO
IF OBJECT_ID('[ventas].[Facturas]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[Facturas] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [NumeroFactura] VARCHAR(20) NOT NULL,
    [CodigoSeguimiento] VARCHAR(10) NOT NULL,
    [FechaHora] DATETIME DEFAULT (getdate()) NOT NULL,
    [UsuarioID] INT NOT NULL,
    [ClienteID] INT NULL,
    [TurnoID] INT NULL,
    [Subtotal] DECIMAL(10,2) NOT NULL,
    [IVA] DECIMAL(10,2) NOT NULL,
    [Total] DECIMAL(10,2) NOT NULL,
    [EsEncargo] BIT DEFAULT ((0)) NOT NULL,
    [IncluyeRUC] BIT DEFAULT ((0)) NOT NULL,
    [EstadoFiscal] VARCHAR(12) DEFAULT ('Emitida') NOT NULL,
    [DocumentoJSON] NVARCHAR(MAX) NULL,
    [AnuladaPor] INT NULL,
    [FechaAnulacion] DATETIME NULL,
    [MotivoAnulacion] NVARCHAR(300) NULL,
    [ClaveSolicitud] VARCHAR(64) NULL,
    CONSTRAINT [PK__Facturas__3214EC276F45D8BC] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Facturas__6A87775475D133FB] UNIQUE ([CodigoSeguimiento])
    );
END
GO
IF OBJECT_ID('[ventas].[FacturasRUC]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[FacturasRUC] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [FacturaID] INT NOT NULL,
    [RazonSocial] VARCHAR(255) NOT NULL,
    [NumeroRUC] VARCHAR(50) NOT NULL,
    CONSTRAINT [PK__Facturas__3214EC27D36E547E] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__Facturas__5C024804462121EF] UNIQUE ([FacturaID])
    );
END
GO
IF OBJECT_ID('[ventas].[Pagos]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[Pagos] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [FacturaID] INT NOT NULL,
    [MetodoPago] VARCHAR(20) NOT NULL,
    [Monto] DECIMAL(10,2) NOT NULL,
    [FechaPago] DATETIME DEFAULT (getdate()) NOT NULL,
    [NombreTransferente] VARCHAR(100) NULL,
    [MonedaRegistro] VARCHAR(6) DEFAULT ('Legacy') NOT NULL,
    [TipoCambioAplicado] DECIMAL(12,6) NULL,
    [TurnoReceptorID] INT NULL,
    [UsuarioReceptorID] INT NULL,
    CONSTRAINT [PK__Pagos__3214EC27572B0517] PRIMARY KEY ([ID]),
    CONSTRAINT [CK_Pagos_MetodoPago] CHECK ([MetodoPago]='Efectivo USD' OR [MetodoPago]='Transferencia' OR [MetodoPago]='Efectivo')
    );
END
GO
IF OBJECT_ID('[ventas].[SecuenciasFiscales]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[SecuenciasFiscales] (
    [Serie] VARCHAR(10) NOT NULL,
    [Ultimo] BIGINT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__Secuenci__798299D6EC6C85DA] PRIMARY KEY ([Serie])
    );
END
GO
IF OBJECT_ID('[ventas].[TipoCambio]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[TipoCambio] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [Fecha] DATE NOT NULL,
    [TasaCompra] DECIMAL(10,4) NOT NULL,
    [TasaVenta] DECIMAL(10,4) NOT NULL,
    [Fuente] VARCHAR(50) DEFAULT ('Manual') NOT NULL,
    CONSTRAINT [PK__TipoCamb__3214EC2749768F44] PRIMARY KEY ([ID]),
    CONSTRAINT [UQ__TipoCamb__B30C8A5EFE6F3000] UNIQUE ([Fecha])
    );
END
GO
IF OBJECT_ID('[ventas].[TurnosCaja]', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[TurnosCaja] (
    [ID] INT IDENTITY(1,1) NOT NULL,
    [UsuarioID] INT NOT NULL,
    [FechaApertura] DATETIME DEFAULT (getdate()) NOT NULL,
    [FechaCierre] DATETIME NULL,
    [EfectivoCalculado] DECIMAL(10,2) NULL,
    [TransferenciasCalculadas] DECIMAL(10,2) NULL,
    [TotalVentaNeta] DECIMAL(10,2) NULL,
    [Cerrado] BIT DEFAULT ((0)) NOT NULL,
    CONSTRAINT [PK__TurnosCa__3214EC278F6ECEFD] PRIMARY KEY ([ID])
    );
END
GO

-- ============================================================================
-- 4. CREACIÓN DE CLAVES FORÁNEAS (FOREIGN KEYS)
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Productos_Categorias' AND parent_object_id = OBJECT_ID('[catalogo].[Productos]'))
BEGIN
    ALTER TABLE [catalogo].[Productos] WITH CHECK ADD CONSTRAINT [FK_Productos_Categorias]
    FOREIGN KEY ([CategoriaID]) REFERENCES [catalogo].[Categorias] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asiento_Periodo' AND parent_object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    ALTER TABLE [contabilidad].[AsientosDiario] WITH CHECK ADD CONSTRAINT [FK_Asiento_Periodo]
    FOREIGN KEY ([PeriodoID]) REFERENCES [contabilidad].[PeriodosContables] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asiento_TipoComprobante' AND parent_object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    ALTER TABLE [contabilidad].[AsientosDiario] WITH CHECK ADD CONSTRAINT [FK_Asiento_TipoComprobante]
    FOREIGN KEY ([TipoComprobanteID]) REFERENCES [contabilidad].[TiposComprobante] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Cuenta_Padre' AND parent_object_id = OBJECT_ID('[contabilidad].[CatalogoCuentas]'))
BEGIN
    ALTER TABLE [contabilidad].[CatalogoCuentas] WITH CHECK ADD CONSTRAINT [FK_Cuenta_Padre]
    FOREIGN KEY ([CuentaPadreID]) REFERENCES [contabilidad].[CatalogoCuentas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Conc_Periodo' AND parent_object_id = OBJECT_ID('[contabilidad].[ConciliacionBancaria]'))
BEGIN
    ALTER TABLE [contabilidad].[ConciliacionBancaria] WITH CHECK ADD CONSTRAINT [FK_Conc_Periodo]
    FOREIGN KEY ([PeriodoID]) REFERENCES [contabilidad].[PeriodosContables] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Conc_Usuario' AND parent_object_id = OBJECT_ID('[contabilidad].[ConciliacionBancaria]'))
BEGIN
    ALTER TABLE [contabilidad].[ConciliacionBancaria] WITH CHECK ADD CONSTRAINT [FK_Conc_Usuario]
    FOREIGN KEY ([RealizadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CxC_Cliente' AND parent_object_id = OBJECT_ID('[contabilidad].[CuentasPorCobrar]'))
BEGIN
    ALTER TABLE [contabilidad].[CuentasPorCobrar] WITH CHECK ADD CONSTRAINT [FK_CxC_Cliente]
    FOREIGN KEY ([ClienteID]) REFERENCES [crm].[Clientes] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CxC_Factura' AND parent_object_id = OBJECT_ID('[contabilidad].[CuentasPorCobrar]'))
BEGIN
    ALTER TABLE [contabilidad].[CuentasPorCobrar] WITH CHECK ADD CONSTRAINT [FK_CxC_Factura]
    FOREIGN KEY ([FacturaID]) REFERENCES [ventas].[Facturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CxP_Proveedor' AND parent_object_id = OBJECT_ID('[contabilidad].[CuentasPorPagar]'))
BEGIN
    ALTER TABLE [contabilidad].[CuentasPorPagar] WITH CHECK ADD CONSTRAINT [FK_CxP_Proveedor]
    FOREIGN KEY ([ProveedorID]) REFERENCES [produccion].[Proveedores] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CxP_Compra' AND parent_object_id = OBJECT_ID('[contabilidad].[CuentasPorPagar]'))
BEGIN
    ALTER TABLE [contabilidad].[CuentasPorPagar] WITH CHECK ADD CONSTRAINT [FK_CxP_Compra]
    FOREIGN KEY ([CompraID]) REFERENCES [produccion].[ComprasMateriaPrima] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Detalle_Asiento' AND parent_object_id = OBJECT_ID('[contabilidad].[DetalleAsientos]'))
BEGIN
    ALTER TABLE [contabilidad].[DetalleAsientos] WITH CHECK ADD CONSTRAINT [FK_Detalle_Asiento]
    FOREIGN KEY ([AsientoID]) REFERENCES [contabilidad].[AsientosDiario] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Detalle_Cuenta' AND parent_object_id = OBJECT_ID('[contabilidad].[DetalleAsientos]'))
BEGIN
    ALTER TABLE [contabilidad].[DetalleAsientos] WITH CHECK ADD CONSTRAINT [FK_Detalle_Cuenta]
    FOREIGN KEY ([CuentaID]) REFERENCES [contabilidad].[CatalogoCuentas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetConc_Conc' AND parent_object_id = OBJECT_ID('[contabilidad].[DetalleConciliacion]'))
BEGIN
    ALTER TABLE [contabilidad].[DetalleConciliacion] WITH CHECK ADD CONSTRAINT [FK_DetConc_Conc]
    FOREIGN KEY ([ConciliacionID]) REFERENCES [contabilidad].[ConciliacionBancaria] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_EgresosPrivados_Usuarios' AND parent_object_id = OBJECT_ID('[contabilidad].[EgresosPrivados]'))
BEGIN
    ALTER TABLE [contabilidad].[EgresosPrivados] WITH CHECK ADD CONSTRAINT [FK_EgresosPrivados_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_PagoCxC_CxC' AND parent_object_id = OBJECT_ID('[contabilidad].[PagosCxC]'))
BEGIN
    ALTER TABLE [contabilidad].[PagosCxC] WITH CHECK ADD CONSTRAINT [FK_PagoCxC_CxC]
    FOREIGN KEY ([CuentaPorCobrarID]) REFERENCES [contabilidad].[CuentasPorCobrar] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_PagoCxC_Asiento' AND parent_object_id = OBJECT_ID('[contabilidad].[PagosCxC]'))
BEGIN
    ALTER TABLE [contabilidad].[PagosCxC] WITH CHECK ADD CONSTRAINT [FK_PagoCxC_Asiento]
    FOREIGN KEY ([AsientoID]) REFERENCES [contabilidad].[AsientosDiario] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Clientes_NivelesConfianza' AND parent_object_id = OBJECT_ID('[crm].[Clientes]'))
BEGIN
    ALTER TABLE [crm].[Clientes] WITH CHECK ADD CONSTRAINT [FK_Clientes_NivelesConfianza]
    FOREIGN KEY ([NivelConfianzaID]) REFERENCES [crm].[NivelesConfianza] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Cotizaciones_Clientes' AND parent_object_id = OBJECT_ID('[crm].[Cotizaciones]'))
BEGIN
    ALTER TABLE [crm].[Cotizaciones] WITH CHECK ADD CONSTRAINT [FK_Cotizaciones_Clientes]
    FOREIGN KEY ([ClienteID]) REFERENCES [crm].[Clientes] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Expor__Revis__51BA1E3A' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Exportaciones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Exportaciones] WITH CHECK ADD CONSTRAINT [FK__DGI_Expor__Revis__51BA1E3A]
    FOREIGN KEY ([RevisionID]) REFERENCES [fiscal].[DGI_Revisiones] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Expor__Usuar__52AE4273' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Exportaciones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Exportaciones] WITH CHECK ADD CONSTRAINT [FK__DGI_Expor__Usuar__52AE4273]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Obser__Revis__4CF5691D' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Observaciones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Observaciones] WITH CHECK ADD CONSTRAINT [FK__DGI_Obser__Revis__4CF5691D]
    FOREIGN KEY ([RevisionID]) REFERENCES [fiscal].[DGI_Revisiones] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Obser__Usuar__4DE98D56' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Observaciones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Observaciones] WITH CHECK ADD CONSTRAINT [FK__DGI_Obser__Usuar__4DE98D56]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Perio__Cread__3DB3258D' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Periodos]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Periodos] WITH CHECK ADD CONSTRAINT [FK__DGI_Perio__Cread__3DB3258D]
    FOREIGN KEY ([CreadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Revis__Perio__4460231C' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Revisiones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Revisiones] WITH CHECK ADD CONSTRAINT [FK__DGI_Revis__Perio__4460231C]
    FOREIGN KEY ([PeriodoID]) REFERENCES [fiscal].[DGI_Periodos] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Revis__Cread__46486B8E' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Revisiones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Revisiones] WITH CHECK ADD CONSTRAINT [FK__DGI_Revis__Cread__46486B8E]
    FOREIGN KEY ([CreadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Revis__Revis__4830B400' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Revisiones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Revisiones] WITH CHECK ADD CONSTRAINT [FK__DGI_Revis__Revis__4830B400]
    FOREIGN KEY ([RevisadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__DGI_Revis__Aprob__4924D839' AND parent_object_id = OBJECT_ID('[fiscal].[DGI_Revisiones]'))
BEGIN
    ALTER TABLE [fiscal].[DGI_Revisiones] WITH CHECK ADD CONSTRAINT [FK__DGI_Revis__Aprob__4924D839]
    FOREIGN KEY ([AprobadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ComprasMP_MateriaPrima' AND parent_object_id = OBJECT_ID('[produccion].[ComprasMateriaPrima]'))
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] WITH CHECK ADD CONSTRAINT [FK_ComprasMP_MateriaPrima]
    FOREIGN KEY ([MateriaPrimaID]) REFERENCES [produccion].[MateriaPrima] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ComprasMP_Proveedores' AND parent_object_id = OBJECT_ID('[produccion].[ComprasMateriaPrima]'))
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] WITH CHECK ADD CONSTRAINT [FK_ComprasMP_Proveedores]
    FOREIGN KEY ([ProveedorID]) REFERENCES [produccion].[Proveedores] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ConsumoLote_MateriaPrima' AND parent_object_id = OBJECT_ID('[produccion].[ConsumoLote]'))
BEGIN
    ALTER TABLE [produccion].[ConsumoLote] WITH CHECK ADD CONSTRAINT [FK_ConsumoLote_MateriaPrima]
    FOREIGN KEY ([MateriaPrimaID]) REFERENCES [produccion].[MateriaPrima] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ConsumoLote_ProduccionLotes' AND parent_object_id = OBJECT_ID('[produccion].[ConsumoLote]'))
BEGIN
    ALTER TABLE [produccion].[ConsumoLote] WITH CHECK ADD CONSTRAINT [FK_ConsumoLote_ProduccionLotes]
    FOREIGN KEY ([LoteID]) REFERENCES [produccion].[ProduccionLotes] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_MateriaPrima_UnidadesMedida' AND parent_object_id = OBJECT_ID('[produccion].[MateriaPrima]'))
BEGIN
    ALTER TABLE [produccion].[MateriaPrima] WITH CHECK ADD CONSTRAINT [FK_MateriaPrima_UnidadesMedida]
    FOREIGN KEY ([UnidadMedidaID]) REFERENCES [catalogo].[UnidadesMedida] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Mermas_Productos' AND parent_object_id = OBJECT_ID('[produccion].[Mermas]'))
BEGIN
    ALTER TABLE [produccion].[Mermas] WITH CHECK ADD CONSTRAINT [FK_Mermas_Productos]
    FOREIGN KEY ([ProductoID]) REFERENCES [catalogo].[Productos] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Mermas_Usuarios' AND parent_object_id = OBJECT_ID('[produccion].[Mermas]'))
BEGIN
    ALTER TABLE [produccion].[Mermas] WITH CHECK ADD CONSTRAINT [FK_Mermas_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ProduccionLotes_Productos' AND parent_object_id = OBJECT_ID('[produccion].[ProduccionLotes]'))
BEGIN
    ALTER TABLE [produccion].[ProduccionLotes] WITH CHECK ADD CONSTRAINT [FK_ProduccionLotes_Productos]
    FOREIGN KEY ([ProductoID]) REFERENCES [catalogo].[Productos] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_RecetaProducto_MateriaPrima' AND parent_object_id = OBJECT_ID('[produccion].[RecetaProducto]'))
BEGIN
    ALTER TABLE [produccion].[RecetaProducto] WITH CHECK ADD CONSTRAINT [FK_RecetaProducto_MateriaPrima]
    FOREIGN KEY ([MateriaPrimaID]) REFERENCES [produccion].[MateriaPrima] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_RecetaProducto_Productos' AND parent_object_id = OBJECT_ID('[produccion].[RecetaProducto]'))
BEGIN
    ALTER TABLE [produccion].[RecetaProducto] WITH CHECK ADD CONSTRAINT [FK_RecetaProducto_Productos]
    FOREIGN KEY ([ProductoID]) REFERENCES [catalogo].[Productos] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asistencia_Empleados' AND parent_object_id = OBJECT_ID('[rrhh].[Asistencia]'))
BEGIN
    ALTER TABLE [rrhh].[Asistencia] WITH CHECK ADD CONSTRAINT [FK_Asistencia_Empleados]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [rrhh].[Empleados] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asistencia_Turnos' AND parent_object_id = OBJECT_ID('[rrhh].[Asistencia]'))
BEGIN
    ALTER TABLE [rrhh].[Asistencia] WITH CHECK ADD CONSTRAINT [FK_Asistencia_Turnos]
    FOREIGN KEY ([TurnoID]) REFERENCES [rrhh].[TurnosLaborales] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asistencia_Usuarios' AND parent_object_id = OBJECT_ID('[rrhh].[Asistencia]'))
BEGIN
    ALTER TABLE [rrhh].[Asistencia] WITH CHECK ADD CONSTRAINT [FK_Asistencia_Usuarios]
    FOREIGN KEY ([RegistradoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DeduccionesJudiciales_Empleados' AND parent_object_id = OBJECT_ID('[rrhh].[DeduccionesJudiciales]'))
BEGIN
    ALTER TABLE [rrhh].[DeduccionesJudiciales] WITH CHECK ADD CONSTRAINT [FK_DeduccionesJudiciales_Empleados]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [rrhh].[Empleados] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetalleNomina_Nomina' AND parent_object_id = OBJECT_ID('[rrhh].[DetalleNomina]'))
BEGIN
    ALTER TABLE [rrhh].[DetalleNomina] WITH CHECK ADD CONSTRAINT [FK_DetalleNomina_Nomina]
    FOREIGN KEY ([NominaID]) REFERENCES [rrhh].[Nomina] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Empleados_Usuarios' AND parent_object_id = OBJECT_ID('[rrhh].[Empleados]'))
BEGIN
    ALTER TABLE [rrhh].[Empleados] WITH CHECK ADD CONSTRAINT [FK_Empleados_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_IncidentesLaborales_Empleados' AND parent_object_id = OBJECT_ID('[rrhh].[IncidentesLaborales]'))
BEGIN
    ALTER TABLE [rrhh].[IncidentesLaborales] WITH CHECK ADD CONSTRAINT [FK_IncidentesLaborales_Empleados]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [rrhh].[Empleados] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_IncidentesLaborales_Registrador' AND parent_object_id = OBJECT_ID('[rrhh].[IncidentesLaborales]'))
BEGIN
    ALTER TABLE [rrhh].[IncidentesLaborales] WITH CHECK ADD CONSTRAINT [FK_IncidentesLaborales_Registrador]
    FOREIGN KEY ([RegistradoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_LicenciasEmpleados_Aprobador' AND parent_object_id = OBJECT_ID('[rrhh].[LicenciasEmpleados]'))
BEGIN
    ALTER TABLE [rrhh].[LicenciasEmpleados] WITH CHECK ADD CONSTRAINT [FK_LicenciasEmpleados_Aprobador]
    FOREIGN KEY ([AprobadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_LicenciasEmpleados_Empleados' AND parent_object_id = OBJECT_ID('[rrhh].[LicenciasEmpleados]'))
BEGIN
    ALTER TABLE [rrhh].[LicenciasEmpleados] WITH CHECK ADD CONSTRAINT [FK_LicenciasEmpleados_Empleados]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [rrhh].[Empleados] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Nomina_Empleados' AND parent_object_id = OBJECT_ID('[rrhh].[Nomina]'))
BEGIN
    ALTER TABLE [rrhh].[Nomina] WITH CHECK ADD CONSTRAINT [FK_Nomina_Empleados]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [rrhh].[Empleados] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Nomina_GeneradoPor' AND parent_object_id = OBJECT_ID('[rrhh].[Nomina]'))
BEGIN
    ALTER TABLE [rrhh].[Nomina] WITH CHECK ADD CONSTRAINT [FK_Nomina_GeneradoPor]
    FOREIGN KEY ([GeneradoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__PerfilesP__Actua__5C57A83E' AND parent_object_id = OBJECT_ID('[rrhh].[PerfilesPuesto]'))
BEGIN
    ALTER TABLE [rrhh].[PerfilesPuesto] WITH CHECK ADD CONSTRAINT [FK__PerfilesP__Actua__5C57A83E]
    FOREIGN KEY ([ActualizadoPor]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ValesEmpleados_Usuarios' AND parent_object_id = OBJECT_ID('[rrhh].[ValesEmpleados]'))
BEGIN
    ALTER TABLE [rrhh].[ValesEmpleados] WITH CHECK ADD CONSTRAINT [FK_ValesEmpleados_Usuarios]
    FOREIGN KEY ([EmpleadoID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_AlertasSMTP_Error' AND parent_object_id = OBJECT_ID('[seguridad].[AlertasSMTPOutbox]'))
BEGIN
    ALTER TABLE [seguridad].[AlertasSMTPOutbox] WITH CHECK ADD CONSTRAINT [FK_AlertasSMTP_Error]
    FOREIGN KEY ([ErrorID]) REFERENCES [seguridad].[BitacoraErrores] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_AuditLog_Usuarios' AND parent_object_id = OBJECT_ID('[seguridad].[AuditLog]'))
BEGIN
    ALTER TABLE [seguridad].[AuditLog] WITH CHECK ADD CONSTRAINT [FK_AuditLog_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Usuarios_Roles' AND parent_object_id = OBJECT_ID('[seguridad].[Usuarios]'))
BEGIN
    ALTER TABLE [seguridad].[Usuarios] WITH CHECK ADD CONSTRAINT [FK_Usuarios_Roles]
    FOREIGN KEY ([RolID]) REFERENCES [seguridad].[Roles] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoLog_Arqueo' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoAuditLog]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoAuditLog] WITH CHECK ADD CONSTRAINT [FK_ArqueoLog_Arqueo]
    FOREIGN KEY ([ArqueoID]) REFERENCES [ventas].[ArqueoCaja] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoLog_Usuario' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoAuditLog]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoAuditLog] WITH CHECK ADD CONSTRAINT [FK_ArqueoLog_Usuario]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoCaja_TurnosCaja' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoCaja]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoCaja] WITH CHECK ADD CONSTRAINT [FK_ArqueoCaja_TurnosCaja]
    FOREIGN KEY ([TurnoID]) REFERENCES [ventas].[TurnosCaja] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoCaja_Usuarios' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoCaja]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoCaja] WITH CHECK ADD CONSTRAINT [FK_ArqueoCaja_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoCaja_Verificador' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoCaja]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoCaja] WITH CHECK ADD CONSTRAINT [FK_ArqueoCaja_Verificador]
    FOREIGN KEY ([VerificadoPorID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_ArqueoDenom_Arqueo' AND parent_object_id = OBJECT_ID('[ventas].[ArqueoDetalleDenominacion]'))
BEGIN
    ALTER TABLE [ventas].[ArqueoDetalleDenominacion] WITH CHECK ADD CONSTRAINT [FK_ArqueoDenom_Arqueo]
    FOREIGN KEY ([ArqueoID]) REFERENCES [ventas].[ArqueoCaja] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetalleFacturas_Facturas' AND parent_object_id = OBJECT_ID('[ventas].[DetalleFacturas]'))
BEGIN
    ALTER TABLE [ventas].[DetalleFacturas] WITH CHECK ADD CONSTRAINT [FK_DetalleFacturas_Facturas]
    FOREIGN KEY ([FacturaID]) REFERENCES [ventas].[Facturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetalleFacturas_Productos' AND parent_object_id = OBJECT_ID('[ventas].[DetalleFacturas]'))
BEGIN
    ALTER TABLE [ventas].[DetalleFacturas] WITH CHECK ADD CONSTRAINT [FK_DetalleFacturas_Productos]
    FOREIGN KEY ([ProductoID]) REFERENCES [catalogo].[Productos] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetalleIngredientes_DetalleFacturas' AND parent_object_id = OBJECT_ID('[ventas].[DetalleIngredientes]'))
BEGIN
    ALTER TABLE [ventas].[DetalleIngredientes] WITH CHECK ADD CONSTRAINT [FK_DetalleIngredientes_DetalleFacturas]
    FOREIGN KEY ([DetalleFacturaID]) REFERENCES [ventas].[DetalleFacturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_DetalleIngredientes_Ingredientes' AND parent_object_id = OBJECT_ID('[ventas].[DetalleIngredientes]'))
BEGIN
    ALTER TABLE [ventas].[DetalleIngredientes] WITH CHECK ADD CONSTRAINT [FK_DetalleIngredientes_Ingredientes]
    FOREIGN KEY ([IngredienteID]) REFERENCES [catalogo].[Ingredientes] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Encargos_Facturas' AND parent_object_id = OBJECT_ID('[ventas].[Encargos]'))
BEGIN
    ALTER TABLE [ventas].[Encargos] WITH CHECK ADD CONSTRAINT [FK_Encargos_Facturas]
    FOREIGN KEY ([FacturaID]) REFERENCES [ventas].[Facturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Facturas_Clientes' AND parent_object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    ALTER TABLE [ventas].[Facturas] WITH CHECK ADD CONSTRAINT [FK_Facturas_Clientes]
    FOREIGN KEY ([ClienteID]) REFERENCES [crm].[Clientes] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Facturas_TurnosCaja' AND parent_object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    ALTER TABLE [ventas].[Facturas] WITH CHECK ADD CONSTRAINT [FK_Facturas_TurnosCaja]
    FOREIGN KEY ([TurnoID]) REFERENCES [ventas].[TurnosCaja] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Facturas_Usuarios' AND parent_object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    ALTER TABLE [ventas].[Facturas] WITH CHECK ADD CONSTRAINT [FK_Facturas_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_FacturasRUC_Facturas' AND parent_object_id = OBJECT_ID('[ventas].[FacturasRUC]'))
BEGIN
    ALTER TABLE [ventas].[FacturasRUC] WITH CHECK ADD CONSTRAINT [FK_FacturasRUC_Facturas]
    FOREIGN KEY ([FacturaID]) REFERENCES [ventas].[Facturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Pagos_Facturas' AND parent_object_id = OBJECT_ID('[ventas].[Pagos]'))
BEGIN
    ALTER TABLE [ventas].[Pagos] WITH CHECK ADD CONSTRAINT [FK_Pagos_Facturas]
    FOREIGN KEY ([FacturaID]) REFERENCES [ventas].[Facturas] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Pagos_TurnoReceptor' AND parent_object_id = OBJECT_ID('[ventas].[Pagos]'))
BEGIN
    ALTER TABLE [ventas].[Pagos] WITH CHECK ADD CONSTRAINT [FK_Pagos_TurnoReceptor]
    FOREIGN KEY ([TurnoReceptorID]) REFERENCES [ventas].[TurnosCaja] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Pagos_UsuarioReceptor' AND parent_object_id = OBJECT_ID('[ventas].[Pagos]'))
BEGIN
    ALTER TABLE [ventas].[Pagos] WITH CHECK ADD CONSTRAINT [FK_Pagos_UsuarioReceptor]
    FOREIGN KEY ([UsuarioReceptorID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_TurnosCaja_Usuarios' AND parent_object_id = OBJECT_ID('[ventas].[TurnosCaja]'))
BEGIN
    ALTER TABLE [ventas].[TurnosCaja] WITH CHECK ADD CONSTRAINT [FK_TurnosCaja_Usuarios]
    FOREIGN KEY ([UsuarioID]) REFERENCES [seguridad].[Usuarios] ([ID]);
END
GO

-- ============================================================================
-- 5. ÍNDICES DE RENDIMIENTO
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Productos_CategoriaID' AND object_id = OBJECT_ID('[catalogo].[Productos]'))
BEGIN
    CREATE INDEX [IX_Productos_CategoriaID] ON [catalogo].[Productos] ([CategoriaID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AsientosDiario_Estado' AND object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    CREATE INDEX [IX_AsientosDiario_Estado] ON [contabilidad].[AsientosDiario] ([Estado]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AsientosDiario_Fecha' AND object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    CREATE INDEX [IX_AsientosDiario_Fecha] ON [contabilidad].[AsientosDiario] ([Fecha]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AsientosDiario_Periodo' AND object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    CREATE INDEX [IX_AsientosDiario_Periodo] ON [contabilidad].[AsientosDiario] ([PeriodoID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_FiscalComprobante' AND object_id = OBJECT_ID('[contabilidad].[AsientosDiario]'))
BEGIN
    CREATE UNIQUE INDEX [UX_FiscalComprobante] ON [contabilidad].[AsientosDiario] ([NumeroComprobante]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CatalogoCuentas_Clase' AND object_id = OBJECT_ID('[contabilidad].[CatalogoCuentas]'))
BEGIN
    CREATE INDEX [IX_CatalogoCuentas_Clase] ON [contabilidad].[CatalogoCuentas] ([Clase]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CatalogoCuentas_Nivel' AND object_id = OBJECT_ID('[contabilidad].[CatalogoCuentas]'))
BEGIN
    CREATE INDEX [IX_CatalogoCuentas_Nivel] ON [contabilidad].[CatalogoCuentas] ([Nivel]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CatalogoCuentas_Padre' AND object_id = OBJECT_ID('[contabilidad].[CatalogoCuentas]'))
BEGIN
    CREATE INDEX [IX_CatalogoCuentas_Padre] ON [contabilidad].[CatalogoCuentas] ([CuentaPadreID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CxC_Cliente' AND object_id = OBJECT_ID('[contabilidad].[CuentasPorCobrar]'))
BEGIN
    CREATE INDEX [IX_CxC_Cliente] ON [contabilidad].[CuentasPorCobrar] ([ClienteID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CxC_Estado' AND object_id = OBJECT_ID('[contabilidad].[CuentasPorCobrar]'))
BEGIN
    CREATE INDEX [IX_CxC_Estado] ON [contabilidad].[CuentasPorCobrar] ([Estado]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CxP_Estado' AND object_id = OBJECT_ID('[contabilidad].[CuentasPorPagar]'))
BEGIN
    CREATE INDEX [IX_CxP_Estado] ON [contabilidad].[CuentasPorPagar] ([Estado]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CxP_Proveedor' AND object_id = OBJECT_ID('[contabilidad].[CuentasPorPagar]'))
BEGIN
    CREATE INDEX [IX_CxP_Proveedor] ON [contabilidad].[CuentasPorPagar] ([ProveedorID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DetalleAsientos_Asiento' AND object_id = OBJECT_ID('[contabilidad].[DetalleAsientos]'))
BEGIN
    CREATE INDEX [IX_DetalleAsientos_Asiento] ON [contabilidad].[DetalleAsientos] ([AsientoID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DetalleAsientos_Cuenta' AND object_id = OBJECT_ID('[contabilidad].[DetalleAsientos]'))
BEGIN
    CREATE INDEX [IX_DetalleAsientos_Cuenta] ON [contabilidad].[DetalleAsientos] ([CuentaID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_FiscalPeriodo' AND object_id = OBJECT_ID('[contabilidad].[PeriodosContables]'))
BEGIN
    CREATE UNIQUE INDEX [UX_FiscalPeriodo] ON [contabilidad].[PeriodosContables] ([Anio], [Mes]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AlertasSMTP_Consumir' AND object_id = OBJECT_ID('[seguridad].[AlertasSMTPOutbox]'))
BEGIN
    CREATE INDEX [IX_AlertasSMTP_Consumir] ON [seguridad].[AlertasSMTPOutbox] ([Estado], [DisponibleDesde], [ErrorID]) INCLUDE ([DedupKey], [LeaseHasta], [Forzar]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuthChallenges_Subject_Kind' AND object_id = OBJECT_ID('[seguridad].[AuthChallenges]'))
BEGIN
    CREATE INDEX [IX_AuthChallenges_Subject_Kind] ON [seguridad].[AuthChallenges] ([Subject], [Kind]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BitacoraErrores_FechaHora' AND object_id = OBJECT_ID('[seguridad].[BitacoraErrores]'))
BEGIN
    CREATE INDEX [IX_BitacoraErrores_FechaHora] ON [seguridad].[BitacoraErrores] ([FechaHora]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BitacoraErrores_Notificado' AND object_id = OBJECT_ID('[seguridad].[BitacoraErrores]'))
BEGIN
    CREATE INDEX [IX_BitacoraErrores_Notificado] ON [seguridad].[BitacoraErrores] ([NotificadoSMTP], [Severidad]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BitacoraErrores_SMTPPendiente' AND object_id = OBJECT_ID('[seguridad].[BitacoraErrores]'))
BEGIN
    CREATE INDEX [IX_BitacoraErrores_SMTPPendiente] ON [seguridad].[BitacoraErrores] ([ID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BloqueosCuenta_BloqueadoHasta' AND object_id = OBJECT_ID('[seguridad].[BloqueosCuenta]'))
BEGIN
    CREATE INDEX [IX_BloqueosCuenta_BloqueadoHasta] ON [seguridad].[BloqueosCuenta] ([Identificador], [BloqueadoHasta]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_DetalleFacturas_FacturaID' AND object_id = OBJECT_ID('[ventas].[DetalleFacturas]'))
BEGIN
    CREATE INDEX [IX_DetalleFacturas_FacturaID] ON [ventas].[DetalleFacturas] ([FacturaID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Encargos_Estado' AND object_id = OBJECT_ID('[ventas].[Encargos]'))
BEGIN
    CREATE INDEX [IX_Encargos_Estado] ON [ventas].[Encargos] ([Estado]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Facturas_ClienteID' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE INDEX [IX_Facturas_ClienteID] ON [ventas].[Facturas] ([ClienteID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Facturas_FechaHora' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE INDEX [IX_Facturas_FechaHora] ON [ventas].[Facturas] ([FechaHora]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Facturas_TurnoID' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE INDEX [IX_Facturas_TurnoID] ON [ventas].[Facturas] ([TurnoID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Facturas_UsuarioID' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE INDEX [IX_Facturas_UsuarioID] ON [ventas].[Facturas] ([UsuarioID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_FiscalNumero' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE UNIQUE INDEX [UX_FiscalNumero] ON [ventas].[Facturas] ([NumeroFactura]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_FiscalSolicitud' AND object_id = OBJECT_ID('[ventas].[Facturas]'))
BEGIN
    CREATE UNIQUE INDEX [UX_FiscalSolicitud] ON [ventas].[Facturas] ([ClaveSolicitud]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Pagos_FacturaID' AND object_id = OBJECT_ID('[ventas].[Pagos]'))
BEGIN
    CREATE INDEX [IX_Pagos_FacturaID] ON [ventas].[Pagos] ([FacturaID]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Pagos_TurnoReceptor' AND object_id = OBJECT_ID('[ventas].[Pagos]'))
BEGIN
    CREATE INDEX [IX_Pagos_TurnoReceptor] ON [ventas].[Pagos] ([TurnoReceptorID]) INCLUDE ([MetodoPago], [Monto], [MonedaRegistro]);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_TurnosCaja_UsuarioID' AND object_id = OBJECT_ID('[ventas].[TurnosCaja]'))
BEGIN
    CREATE INDEX [IX_TurnosCaja_UsuarioID] ON [ventas].[TurnosCaja] ([UsuarioID]);
END
GO

-- ============================================================================
-- 6. SINÓNIMOS EN ESQUEMA [dbo] PARA COMPATIBILIDAD RETROACTIVA
-- ============================================================================

IF OBJECT_ID('dbo.[Categorias]', 'SN') IS NULL AND OBJECT_ID('dbo.[Categorias]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Categorias] FOR [catalogo].[Categorias]');
GO
IF OBJECT_ID('dbo.[Ingredientes]', 'SN') IS NULL AND OBJECT_ID('dbo.[Ingredientes]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Ingredientes] FOR [catalogo].[Ingredientes]');
GO
IF OBJECT_ID('dbo.[Productos]', 'SN') IS NULL AND OBJECT_ID('dbo.[Productos]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Productos] FOR [catalogo].[Productos]');
GO
IF OBJECT_ID('dbo.[UnidadesMedida]', 'SN') IS NULL AND OBJECT_ID('dbo.[UnidadesMedida]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[UnidadesMedida] FOR [catalogo].[UnidadesMedida]');
GO
IF OBJECT_ID('dbo.[AsientosDiario]', 'SN') IS NULL AND OBJECT_ID('dbo.[AsientosDiario]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[AsientosDiario] FOR [contabilidad].[AsientosDiario]');
GO
IF OBJECT_ID('dbo.[CatalogoCuentas]', 'SN') IS NULL AND OBJECT_ID('dbo.[CatalogoCuentas]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[CatalogoCuentas] FOR [contabilidad].[CatalogoCuentas]');
GO
IF OBJECT_ID('dbo.[ConciliacionBancaria]', 'SN') IS NULL AND OBJECT_ID('dbo.[ConciliacionBancaria]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ConciliacionBancaria] FOR [contabilidad].[ConciliacionBancaria]');
GO
IF OBJECT_ID('dbo.[CuentasPorCobrar]', 'SN') IS NULL AND OBJECT_ID('dbo.[CuentasPorCobrar]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[CuentasPorCobrar] FOR [contabilidad].[CuentasPorCobrar]');
GO
IF OBJECT_ID('dbo.[CuentasPorPagar]', 'SN') IS NULL AND OBJECT_ID('dbo.[CuentasPorPagar]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[CuentasPorPagar] FOR [contabilidad].[CuentasPorPagar]');
GO
IF OBJECT_ID('dbo.[DetalleAsientos]', 'SN') IS NULL AND OBJECT_ID('dbo.[DetalleAsientos]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DetalleAsientos] FOR [contabilidad].[DetalleAsientos]');
GO
IF OBJECT_ID('dbo.[DetalleConciliacion]', 'SN') IS NULL AND OBJECT_ID('dbo.[DetalleConciliacion]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DetalleConciliacion] FOR [contabilidad].[DetalleConciliacion]');
GO
IF OBJECT_ID('dbo.[EgresosPrivados]', 'SN') IS NULL AND OBJECT_ID('dbo.[EgresosPrivados]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[EgresosPrivados] FOR [contabilidad].[EgresosPrivados]');
GO
IF OBJECT_ID('dbo.[PagosCxC]', 'SN') IS NULL AND OBJECT_ID('dbo.[PagosCxC]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[PagosCxC] FOR [contabilidad].[PagosCxC]');
GO
IF OBJECT_ID('dbo.[PeriodosContables]', 'SN') IS NULL AND OBJECT_ID('dbo.[PeriodosContables]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[PeriodosContables] FOR [contabilidad].[PeriodosContables]');
GO
IF OBJECT_ID('dbo.[TiposComprobante]', 'SN') IS NULL AND OBJECT_ID('dbo.[TiposComprobante]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[TiposComprobante] FOR [contabilidad].[TiposComprobante]');
GO
IF OBJECT_ID('dbo.[Clientes]', 'SN') IS NULL AND OBJECT_ID('dbo.[Clientes]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Clientes] FOR [crm].[Clientes]');
GO
IF OBJECT_ID('dbo.[Cotizaciones]', 'SN') IS NULL AND OBJECT_ID('dbo.[Cotizaciones]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Cotizaciones] FOR [crm].[Cotizaciones]');
GO
IF OBJECT_ID('dbo.[NivelesConfianza]', 'SN') IS NULL AND OBJECT_ID('dbo.[NivelesConfianza]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[NivelesConfianza] FOR [crm].[NivelesConfianza]');
GO
IF OBJECT_ID('dbo.[BitacoraFiscal]', 'SN') IS NULL AND OBJECT_ID('dbo.[BitacoraFiscal]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[BitacoraFiscal] FOR [fiscal].[BitacoraFiscal]');
GO
IF OBJECT_ID('dbo.[DGI_Exportaciones]', 'SN') IS NULL AND OBJECT_ID('dbo.[DGI_Exportaciones]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DGI_Exportaciones] FOR [fiscal].[DGI_Exportaciones]');
GO
IF OBJECT_ID('dbo.[DGI_Observaciones]', 'SN') IS NULL AND OBJECT_ID('dbo.[DGI_Observaciones]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DGI_Observaciones] FOR [fiscal].[DGI_Observaciones]');
GO
IF OBJECT_ID('dbo.[DGI_Periodos]', 'SN') IS NULL AND OBJECT_ID('dbo.[DGI_Periodos]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DGI_Periodos] FOR [fiscal].[DGI_Periodos]');
GO
IF OBJECT_ID('dbo.[DGI_Revisiones]', 'SN') IS NULL AND OBJECT_ID('dbo.[DGI_Revisiones]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DGI_Revisiones] FOR [fiscal].[DGI_Revisiones]');
GO
IF OBJECT_ID('dbo.[ComprasMateriaPrima]', 'SN') IS NULL AND OBJECT_ID('dbo.[ComprasMateriaPrima]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ComprasMateriaPrima] FOR [produccion].[ComprasMateriaPrima]');
GO
IF OBJECT_ID('dbo.[ConsumoLote]', 'SN') IS NULL AND OBJECT_ID('dbo.[ConsumoLote]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ConsumoLote] FOR [produccion].[ConsumoLote]');
GO
IF OBJECT_ID('dbo.[MateriaPrima]', 'SN') IS NULL AND OBJECT_ID('dbo.[MateriaPrima]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[MateriaPrima] FOR [produccion].[MateriaPrima]');
GO
IF OBJECT_ID('dbo.[Mermas]', 'SN') IS NULL AND OBJECT_ID('dbo.[Mermas]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Mermas] FOR [produccion].[Mermas]');
GO
IF OBJECT_ID('dbo.[ProduccionLotes]', 'SN') IS NULL AND OBJECT_ID('dbo.[ProduccionLotes]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ProduccionLotes] FOR [produccion].[ProduccionLotes]');
GO
IF OBJECT_ID('dbo.[Proveedores]', 'SN') IS NULL AND OBJECT_ID('dbo.[Proveedores]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Proveedores] FOR [produccion].[Proveedores]');
GO
IF OBJECT_ID('dbo.[RecetaProducto]', 'SN') IS NULL AND OBJECT_ID('dbo.[RecetaProducto]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[RecetaProducto] FOR [produccion].[RecetaProducto]');
GO
IF OBJECT_ID('dbo.[Asistencia]', 'SN') IS NULL AND OBJECT_ID('dbo.[Asistencia]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Asistencia] FOR [rrhh].[Asistencia]');
GO
IF OBJECT_ID('dbo.[DeduccionesJudiciales]', 'SN') IS NULL AND OBJECT_ID('dbo.[DeduccionesJudiciales]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DeduccionesJudiciales] FOR [rrhh].[DeduccionesJudiciales]');
GO
IF OBJECT_ID('dbo.[DetalleNomina]', 'SN') IS NULL AND OBJECT_ID('dbo.[DetalleNomina]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DetalleNomina] FOR [rrhh].[DetalleNomina]');
GO
IF OBJECT_ID('dbo.[Empleados]', 'SN') IS NULL AND OBJECT_ID('dbo.[Empleados]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Empleados] FOR [rrhh].[Empleados]');
GO
IF OBJECT_ID('dbo.[FeriadosNacionales]', 'SN') IS NULL AND OBJECT_ID('dbo.[FeriadosNacionales]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[FeriadosNacionales] FOR [rrhh].[FeriadosNacionales]');
GO
IF OBJECT_ID('dbo.[IncidentesLaborales]', 'SN') IS NULL AND OBJECT_ID('dbo.[IncidentesLaborales]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[IncidentesLaborales] FOR [rrhh].[IncidentesLaborales]');
GO
IF OBJECT_ID('dbo.[LicenciasEmpleados]', 'SN') IS NULL AND OBJECT_ID('dbo.[LicenciasEmpleados]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[LicenciasEmpleados] FOR [rrhh].[LicenciasEmpleados]');
GO
IF OBJECT_ID('dbo.[Nomina]', 'SN') IS NULL AND OBJECT_ID('dbo.[Nomina]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Nomina] FOR [rrhh].[Nomina]');
GO
IF OBJECT_ID('dbo.[PerfilesPuesto]', 'SN') IS NULL AND OBJECT_ID('dbo.[PerfilesPuesto]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[PerfilesPuesto] FOR [rrhh].[PerfilesPuesto]');
GO
IF OBJECT_ID('dbo.[TurnosLaborales]', 'SN') IS NULL AND OBJECT_ID('dbo.[TurnosLaborales]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[TurnosLaborales] FOR [rrhh].[TurnosLaborales]');
GO
IF OBJECT_ID('dbo.[ValesEmpleados]', 'SN') IS NULL AND OBJECT_ID('dbo.[ValesEmpleados]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ValesEmpleados] FOR [rrhh].[ValesEmpleados]');
GO
IF OBJECT_ID('dbo.[escala_salarial]', 'SN') IS NULL AND OBJECT_ID('dbo.[escala_salarial]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[escala_salarial] FOR [rrhh].[escala_salarial]');
GO
IF OBJECT_ID('dbo.[AlertasSMTPDedup]', 'SN') IS NULL AND OBJECT_ID('dbo.[AlertasSMTPDedup]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[AlertasSMTPDedup] FOR [seguridad].[AlertasSMTPDedup]');
GO
IF OBJECT_ID('dbo.[AlertasSMTPOutbox]', 'SN') IS NULL AND OBJECT_ID('dbo.[AlertasSMTPOutbox]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[AlertasSMTPOutbox] FOR [seguridad].[AlertasSMTPOutbox]');
GO
IF OBJECT_ID('dbo.[AuditLog]', 'SN') IS NULL AND OBJECT_ID('dbo.[AuditLog]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[AuditLog] FOR [seguridad].[AuditLog]');
GO
IF OBJECT_ID('dbo.[AuthChallenges]', 'SN') IS NULL AND OBJECT_ID('dbo.[AuthChallenges]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[AuthChallenges] FOR [seguridad].[AuthChallenges]');
GO
IF OBJECT_ID('dbo.[BitacoraErrores]', 'SN') IS NULL AND OBJECT_ID('dbo.[BitacoraErrores]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[BitacoraErrores] FOR [seguridad].[BitacoraErrores]');
GO
IF OBJECT_ID('dbo.[BloqueosCuenta]', 'SN') IS NULL AND OBJECT_ID('dbo.[BloqueosCuenta]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[BloqueosCuenta] FOR [seguridad].[BloqueosCuenta]');
GO
IF OBJECT_ID('dbo.[ConfiguracionSistema]', 'SN') IS NULL AND OBJECT_ID('dbo.[ConfiguracionSistema]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ConfiguracionSistema] FOR [seguridad].[ConfiguracionSistema]');
GO
IF OBJECT_ID('dbo.[Roles]', 'SN') IS NULL AND OBJECT_ID('dbo.[Roles]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Roles] FOR [seguridad].[Roles]');
GO
IF OBJECT_ID('dbo.[Usuarios]', 'SN') IS NULL AND OBJECT_ID('dbo.[Usuarios]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Usuarios] FOR [seguridad].[Usuarios]');
GO
IF OBJECT_ID('dbo.[ArqueoAuditLog]', 'SN') IS NULL AND OBJECT_ID('dbo.[ArqueoAuditLog]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ArqueoAuditLog] FOR [ventas].[ArqueoAuditLog]');
GO
IF OBJECT_ID('dbo.[ArqueoCaja]', 'SN') IS NULL AND OBJECT_ID('dbo.[ArqueoCaja]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ArqueoCaja] FOR [ventas].[ArqueoCaja]');
GO
IF OBJECT_ID('dbo.[ArqueoDetalleDenominacion]', 'SN') IS NULL AND OBJECT_ID('dbo.[ArqueoDetalleDenominacion]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[ArqueoDetalleDenominacion] FOR [ventas].[ArqueoDetalleDenominacion]');
GO
IF OBJECT_ID('dbo.[DetalleFacturas]', 'SN') IS NULL AND OBJECT_ID('dbo.[DetalleFacturas]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DetalleFacturas] FOR [ventas].[DetalleFacturas]');
GO
IF OBJECT_ID('dbo.[DetalleIngredientes]', 'SN') IS NULL AND OBJECT_ID('dbo.[DetalleIngredientes]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[DetalleIngredientes] FOR [ventas].[DetalleIngredientes]');
GO
IF OBJECT_ID('dbo.[Encargos]', 'SN') IS NULL AND OBJECT_ID('dbo.[Encargos]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Encargos] FOR [ventas].[Encargos]');
GO
IF OBJECT_ID('dbo.[Facturas]', 'SN') IS NULL AND OBJECT_ID('dbo.[Facturas]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Facturas] FOR [ventas].[Facturas]');
GO
IF OBJECT_ID('dbo.[FacturasRUC]', 'SN') IS NULL AND OBJECT_ID('dbo.[FacturasRUC]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[FacturasRUC] FOR [ventas].[FacturasRUC]');
GO
IF OBJECT_ID('dbo.[Pagos]', 'SN') IS NULL AND OBJECT_ID('dbo.[Pagos]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[Pagos] FOR [ventas].[Pagos]');
GO
IF OBJECT_ID('dbo.[SecuenciasFiscales]', 'SN') IS NULL AND OBJECT_ID('dbo.[SecuenciasFiscales]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[SecuenciasFiscales] FOR [ventas].[SecuenciasFiscales]');
GO
IF OBJECT_ID('dbo.[TipoCambio]', 'SN') IS NULL AND OBJECT_ID('dbo.[TipoCambio]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[TipoCambio] FOR [ventas].[TipoCambio]');
GO
IF OBJECT_ID('dbo.[TurnosCaja]', 'SN') IS NULL AND OBJECT_ID('dbo.[TurnosCaja]', 'U') IS NULL
    EXEC('CREATE SYNONYM [dbo].[TurnosCaja] FOR [ventas].[TurnosCaja]');
GO

-- ============================================================================
-- 7. TRIGGERS DE SEGURIDAD, INMUTABILIDAD Y PROTECCIÓN DDL
-- ============================================================================
-- ============================================================================
-- 6. TRIGGERS DE INMUTABILIDAD (AUDITORÍA, ERRORES Y DOCUMENTOS FISCALES)
-- ============================================================================

-- 6.1 Inmutabilidad de seguridad.AuditLog
IF OBJECT_ID('seguridad.AuditLog', 'U') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [seguridad].[TR_AuditLog_Inmutable]
    ON [seguridad].[AuditLog]
    INSTEAD OF UPDATE, DELETE
    AS
    BEGIN
        SET NOCOUNT ON;
        THROW 51006, ''La bitácora de auditoría (seguridad.AuditLog) es inmutable y no permite edición ni borrado.'', 1;
    END
    ');
END
GO

-- 6.2 Inmutabilidad de seguridad.BitacoraErrores (permite únicamente marcar NotificadoSMTP)
IF OBJECT_ID('seguridad.BitacoraErrores', 'U') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [seguridad].[TR_BitacoraErrores_Inmutable]
    ON [seguridad].[BitacoraErrores]
    AFTER UPDATE, DELETE
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (SELECT 1 FROM deleted d LEFT JOIN inserted i ON i.ID = d.ID WHERE i.ID IS NULL)
            THROW 51007, ''La bitácora de errores (seguridad.BitacoraErrores) no permite eliminar registros.'', 1;

        IF EXISTS (
            SELECT 1
            FROM deleted d
            JOIN inserted i ON i.ID = d.ID
            WHERE d.FechaHora <> i.FechaHora
               OR d.Origen <> i.Origen
               OR d.Severidad <> i.Severidad
               OR ISNULL(d.NumeroError, -2147483648) <> ISNULL(i.NumeroError, -2147483648)
               OR ISNULL(d.EstadoError, -2147483648) <> ISNULL(i.EstadoError, -2147483648)
               OR ISNULL(d.LineaError, -2147483648) <> ISNULL(i.LineaError, -2147483648)
               OR ISNULL(d.Procedimiento, N''__NULL__'') <> ISNULL(i.Procedimiento, N''__NULL__'')
               OR ISNULL(d.EsquemaOrigen, N''__NULL__'') <> ISNULL(i.EsquemaOrigen, N''__NULL__'')
               OR d.MensajeError <> i.MensajeError
               OR ISNULL(d.DetalleTecnico, N''__NULL__'') <> ISNULL(i.DetalleTecnico, N''__NULL__'')
               OR ISNULL(d.ParametrosJSON, N''__NULL__'') <> ISNULL(i.ParametrosJSON, N''__NULL__'')
               OR ISNULL(d.UsuarioID, -2147483648) <> ISNULL(i.UsuarioID, -2147483648)
               OR ISNULL(d.Username, N''__NULL__'') <> ISNULL(i.Username, N''__NULL__'')
               OR ISNULL(d.RolAplicacion, N''__NULL__'') <> ISNULL(i.RolAplicacion, N''__NULL__'')
               OR d.UsuarioBD <> i.UsuarioBD
               OR ISNULL(d.DireccionIP, ''__NULL__'') <> ISNULL(i.DireccionIP, ''__NULL__'')
               OR ISNULL(d.RutaHTTP, N''__NULL__'') <> ISNULL(i.RutaHTTP, N''__NULL__'')
               OR (d.NotificadoSMTP = 1 AND i.NotificadoSMTP = 0)
        )
            THROW 51008, ''No se permite alterar el contenido original de un error registrado en seguridad.BitacoraErrores.'', 1;
    END
    ');
END
GO

-- 6.3 Triggers fiscales actualizados sobre sus esquemas definitivos
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL
   AND COL_LENGTH('ventas.Facturas', 'DocumentoJSON') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [ventas].[TR_FiscalFacturaInmutable]
    ON [ventas].[Facturas]
    AFTER UPDATE, DELETE
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (SELECT 1 FROM deleted d LEFT JOIN inserted i ON i.ID = d.ID WHERE i.ID IS NULL)
            THROW 51001, ''Las facturas se anulan, no se eliminan.'', 1;
        IF EXISTS (
            SELECT 1 FROM deleted d JOIN inserted i ON i.ID = d.ID
            WHERE d.NumeroFactura <> i.NumeroFactura
               OR d.Total <> i.Total
               OR d.Subtotal <> i.Subtotal
               OR d.IVA <> i.IVA
               OR (d.DocumentoJSON IS NOT NULL AND (i.DocumentoJSON IS NULL OR d.DocumentoJSON <> i.DocumentoJSON))
        )
            THROW 51002, ''No se puede alterar una factura emitida.'', 1;
    END
    ');
END
GO

IF OBJECT_ID('fiscal.BitacoraFiscal', 'U') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [fiscal].[TR_FiscalBitacoraInmutable]
    ON [fiscal].[BitacoraFiscal]
    INSTEAD OF UPDATE, DELETE
    AS
    BEGIN
        THROW 51003, ''La bitácora fiscal no permite edición ni borrado.'', 1;
    END
    ');
END
GO

IF OBJECT_ID('ventas.DetalleFacturas', 'U') IS NOT NULL
   AND OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL
   AND COL_LENGTH('ventas.Facturas', 'DocumentoJSON') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [ventas].[TR_FiscalDetalleInmutable]
    ON [ventas].[DetalleFacturas]
    AFTER UPDATE, DELETE
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (
            SELECT 1
            FROM (SELECT FacturaID FROM inserted UNION SELECT FacturaID FROM deleted) d
            JOIN [ventas].[Facturas] f ON f.ID = d.FacturaID
            WHERE f.DocumentoJSON IS NOT NULL
        )
            THROW 51004, ''No se puede alterar el detalle de una factura emitida.'', 1;
    END
    ');
END
GO

IF OBJECT_ID('contabilidad.DetalleAsientos', 'U') IS NOT NULL
   AND OBJECT_ID('contabilidad.AsientosDiario', 'U') IS NOT NULL
BEGIN
    EXEC('
    CREATE OR ALTER TRIGGER [contabilidad].[TR_FiscalAsientoDetalleInmutable]
    ON [contabilidad].[DetalleAsientos]
    AFTER UPDATE, DELETE
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (
            SELECT 1
            FROM deleted d
            JOIN [contabilidad].[AsientosDiario] a ON a.ID = d.AsientoID
            WHERE a.Estado IN (''Contabilizado'', ''Anulado'')
        )
            THROW 51005, ''Corrija el asiento mediante reversión, no editando sus líneas.'', 1;
    END
    ');
END
GO

-- 6.4 Asegurar columnas aditivas de migraciones fiscales, contables y RRHH si aún no existen
IF OBJECT_ID('rrhh.Empleados', 'U') IS NOT NULL AND COL_LENGTH('rrhh.Empleados', 'FotoPerfil') IS NULL
    ALTER TABLE [rrhh].[Empleados] ADD FotoPerfil VARCHAR(255) NULL;
IF OBJECT_ID('contabilidad.AsientosDiario', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.AsientosDiario', 'EmisorJSON') IS NULL
    ALTER TABLE [contabilidad].[AsientosDiario] ADD EmisorJSON NVARCHAR(MAX) NULL;
IF OBJECT_ID('contabilidad.DetalleAsientos', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.DetalleAsientos', 'Descripcion') IS NULL
    ALTER TABLE [contabilidad].[DetalleAsientos] ADD Descripcion VARCHAR(255) NULL;
IF OBJECT_ID('contabilidad.DetalleAsientos', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.DetalleAsientos', 'DocumentoRelacionado') IS NULL
    ALTER TABLE [contabilidad].[DetalleAsientos] ADD DocumentoRelacionado VARCHAR(50) NULL;
IF OBJECT_ID('contabilidad.PeriodosContables', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.PeriodosContables', 'CerradoPor') IS NULL
    ALTER TABLE [contabilidad].[PeriodosContables] ADD CerradoPor INT NULL;
IF OBJECT_ID('contabilidad.PeriodosContables', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.PeriodosContables', 'CerradoEn') IS NULL
    ALTER TABLE [contabilidad].[PeriodosContables] ADD CerradoEn DATETIME NULL;
IF OBJECT_ID('contabilidad.PeriodosContables', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.PeriodosContables', 'CierreReservaLegal') IS NULL
    ALTER TABLE [contabilidad].[PeriodosContables] ADD CierreReservaLegal DECIMAL(18,2) NULL;
IF OBJECT_ID('contabilidad.PeriodosContables', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.PeriodosContables', 'CierreUtilidad') IS NULL
    ALTER TABLE [contabilidad].[PeriodosContables] ADD CierreUtilidad DECIMAL(18,2) NULL;
IF OBJECT_ID('contabilidad.CatalogoCuentas', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.CatalogoCuentas', 'Descripcion') IS NULL
    ALTER TABLE [contabilidad].[CatalogoCuentas] ADD Descripcion VARCHAR(255) NULL;
IF OBJECT_ID('contabilidad.CatalogoCuentas', 'U') IS NOT NULL AND COL_LENGTH('contabilidad.CatalogoCuentas', 'OrdenVisualizacion') IS NULL
    ALTER TABLE [contabilidad].[CatalogoCuentas] ADD OrdenVisualizacion INT NOT NULL DEFAULT 0;
IF OBJECT_ID('produccion.ComprasMateriaPrima', 'U') IS NOT NULL AND COL_LENGTH('produccion.ComprasMateriaPrima', 'FacturaProveedor') IS NULL
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD FacturaProveedor NVARCHAR(100) NULL;
IF OBJECT_ID('produccion.ComprasMateriaPrima', 'U') IS NOT NULL AND COL_LENGTH('produccion.ComprasMateriaPrima', 'IVADocumentado') IS NULL
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD IVADocumentado DECIMAL(18,2) NOT NULL DEFAULT 0;
IF OBJECT_ID('ventas.Pagos', 'U') IS NOT NULL AND COL_LENGTH('ventas.Pagos', 'MonedaRegistro') IS NULL
    ALTER TABLE [ventas].[Pagos] ADD MonedaRegistro VARCHAR(6) NOT NULL DEFAULT 'Legacy';
IF OBJECT_ID('ventas.Pagos', 'U') IS NOT NULL AND COL_LENGTH('ventas.Pagos', 'TipoCambioAplicado') IS NULL
    ALTER TABLE [ventas].[Pagos] ADD TipoCambioAplicado DECIMAL(12,6) NULL;
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'EstadoFiscal') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD EstadoFiscal VARCHAR(12) NOT NULL DEFAULT 'Emitida';
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'DocumentoJSON') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD DocumentoJSON NVARCHAR(MAX) NULL;
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'AnuladaPor') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD AnuladaPor INT NULL;
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'FechaAnulacion') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD FechaAnulacion DATETIME NULL;
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'MotivoAnulacion') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD MotivoAnulacion NVARCHAR(300) NULL;
IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL AND COL_LENGTH('ventas.Facturas', 'ClaveSolicitud') IS NULL
    ALTER TABLE [ventas].[Facturas] ADD ClaveSolicitud VARCHAR(64) NULL;
IF OBJECT_ID('catalogo.Productos', 'U') IS NOT NULL AND COL_LENGTH('catalogo.Productos', 'TasaIVA') IS NULL
    ALTER TABLE [catalogo].[Productos] ADD TasaIVA DECIMAL(5,2) NULL;
IF OBJECT_ID('catalogo.Productos', 'U') IS NOT NULL AND COL_LENGTH('catalogo.Productos', 'MotivoExencion') IS NULL
    ALTER TABLE [catalogo].[Productos] ADD MotivoExencion NVARCHAR(200) NULL;
IF OBJECT_ID('contabilidad.TiposComprobante', 'U') IS NULL
BEGIN
    CREATE TABLE [contabilidad].[TiposComprobante] (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        Codigo VARCHAR(5) NOT NULL UNIQUE,
        Nombre VARCHAR(50) NOT NULL,
        Prefijo VARCHAR(10) NOT NULL,
        CorrelativoActual INT NOT NULL DEFAULT 0,
        Activo BIT NOT NULL DEFAULT 1
    );
    IF OBJECT_ID('dbo.TiposComprobante', 'SN') IS NULL AND OBJECT_ID('dbo.TiposComprobante', 'U') IS NULL
        EXEC('CREATE SYNONYM [dbo].[TiposComprobante] FOR [contabilidad].[TiposComprobante];');
END
GO

-- 6.5 Trigger DDL de protección contra borrado de tablas de dominio (DROP_TABLE)
-- Atribución de caja: NULL identifica movimientos históricos aún no conciliados.
-- No inferir el receptor desde la factura: un saldo puede cobrarse en otro turno.
IF COL_LENGTH('ventas.Pagos', 'TurnoReceptorID') IS NULL
    ALTER TABLE [ventas].[Pagos] ADD TurnoReceptorID INT NULL;
IF COL_LENGTH('ventas.Pagos', 'UsuarioReceptorID') IS NULL
    ALTER TABLE [ventas].[Pagos] ADD UsuarioReceptorID INT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name='FK_Pagos_TurnoReceptor')
    ALTER TABLE [ventas].[Pagos] ADD CONSTRAINT FK_Pagos_TurnoReceptor FOREIGN KEY (TurnoReceptorID) REFERENCES [ventas].[TurnosCaja](ID);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name='FK_Pagos_UsuarioReceptor')
    ALTER TABLE [ventas].[Pagos] ADD CONSTRAINT FK_Pagos_UsuarioReceptor FOREIGN KEY (UsuarioReceptorID) REFERENCES [seguridad].[Usuarios](ID);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('ventas.Pagos') AND name='IX_Pagos_TurnoReceptor')
    CREATE INDEX IX_Pagos_TurnoReceptor ON [ventas].[Pagos](TurnoReceptorID) INCLUDE (MetodoPago,Monto,MonedaRegistro);
GO

-- La búsqueda fiscal siempre empieza por el rango mensual y pagina en SQL Server.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('ventas.Facturas') AND name='IX_Facturas_FiscalFecha')
    CREATE INDEX IX_Facturas_FiscalFecha ON [ventas].[Facturas](FechaHora DESC, ID DESC)
        INCLUDE (NumeroFactura, ClienteID, EstadoFiscal, EsEncargo, Total);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('ventas.Facturas') AND name='IX_Facturas_FiscalNumero')
    CREATE INDEX IX_Facturas_FiscalNumero ON [ventas].[Facturas](NumeroFactura, FechaHora DESC)
        INCLUDE (ClienteID, EstadoFiscal, EsEncargo, Total);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('ventas.Facturas') AND name='IX_Facturas_FiscalCliente')
    CREATE INDEX IX_Facturas_FiscalCliente ON [ventas].[Facturas](ClienteID, FechaHora DESC)
        INCLUDE (NumeroFactura, EstadoFiscal, EsEncargo, Total);
GO

-- Cargo permanece en Empleados por compatibilidad; el catálogo describe el rol, no su salario.
IF OBJECT_ID('rrhh.PerfilesPuesto', 'U') IS NULL
    CREATE TABLE [rrhh].[PerfilesPuesto] (
        Cargo NVARCHAR(100) NOT NULL PRIMARY KEY,
        PerfilPuesto NVARCHAR(1000) NOT NULL CONSTRAINT DF_PerfilesPuesto_Perfil DEFAULT N'',
        Obligaciones NVARCHAR(2000) NOT NULL CONSTRAINT DF_PerfilesPuesto_Obligaciones DEFAULT N'',
        RequisitosCompetencias NVARCHAR(1000) NOT NULL CONSTRAINT DF_PerfilesPuesto_Requisitos DEFAULT N'',
        ActualizadoEn DATETIME2 NOT NULL CONSTRAINT DF_PerfilesPuesto_Fecha DEFAULT SYSUTCDATETIME(),
        ActualizadoPor INT NULL REFERENCES [seguridad].[Usuarios](ID)
    );
GO
INSERT INTO [rrhh].[PerfilesPuesto](Cargo)
SELECT DISTINCT LTRIM(RTRIM(e.Cargo)) FROM [rrhh].[Empleados] e
WHERE NULLIF(LTRIM(RTRIM(e.Cargo)),N'') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM [rrhh].[PerfilesPuesto] p WHERE p.Cargo=LTRIM(RTRIM(e.Cargo)));
GO

EXEC('
CREATE OR ALTER TRIGGER [TR_DDL_ProteccionEsquemas]
ON DATABASE
FOR DROP_TABLE
AS
BEGIN
    SET NOCOUNT ON;
    IF TRY_CAST(SESSION_CONTEXT(N''allow_ddl_migration'') AS INT) = 1
        RETURN;

    DECLARE @EventData XML = EVENTDATA();
    DECLARE @SchemaName NVARCHAR(128) = @EventData.value(''(/EVENT_INSTANCE/SchemaName)[1]'', ''NVARCHAR(128)'');
    DECLARE @ObjectName NVARCHAR(128) = @EventData.value(''(/EVENT_INSTANCE/ObjectName)[1]'', ''NVARCHAR(128)'');

    IF @SchemaName IN (N''seguridad'', N''crm'', N''catalogo'', N''ventas'', N''produccion'', N''rrhh'', N''contabilidad'', N''fiscal'')
    BEGIN
        THROW 51009, ''Operación DDL bloqueada: No se permite eliminar tablas de los esquemas de dominio protegidos (TR_DDL_ProteccionEsquemas).'', 1;
    END
END
');
GO


-- ============================================================================
-- 8. MATRIZ DE ROLES (RBAC), DYNAMIC DATA MASKING (DDM) Y MENOR PRIVILEGIO
-- ============================================================================
/* ============================================================================
   PANADERÍA Y REPOSTERÍA BRAJHER'S CAKE (PANADERÍA AMADA)
   ARCHIVO: 02_roles_y_seguridad_bd.sql
   PROPÓSITO:
     1. Definición de los 6 Roles Nativos de Base de Datos (RBAC SQL Server):
        - db_rol_superadmin     (Administración técnica, auditoría y bitácora de errores)
        - db_rol_gerencia       (Gerencia/Admin: Dashboard, Contabilidad, Fiscal, DGI, RRHH)
        - db_rol_cajero_pos     (Cajero Estándar: POS, Turnos, Facturación, Arqueo Etapa 1)
        - db_rol_produccion     (Operativo/Cocina: Monitor, Lotes, Recetas, Mermas)
        - db_rol_kiosco         (Kiosco Biométrico: Asistencia y descriptores faciales)
        - db_rol_portal_cliente (Cliente/Invitado: Catálogo público, Cotizaciones propias, Seguimiento)
     2. Creación de usuarios contenidos (WITHOUT LOGIN) para aislamiento y pruebas
        de contexto de ejecución (EXECUTE AS USER).
     3. Enmascaramiento Dinámico de Datos (Dynamic Data Masking - DDM) en columnas
        altamente sensibles (TOTPSecret, Cedula, NumeroINSS, FaceDescriptor).
     4. Denegación estricta (DENY SELECT, INSERT, UPDATE, DELETE) sobre tablas base
        y sinónimos para forzar el acceso exclusivamente vía Stored Procedures
        (Ownership Chaining).
   ============================================================================ */

SET NOCOUNT ON;
GO

-- ============================================================================
-- 1. CREACIÓN IDEMPOTENTE DE LOS 6 ROLES DE BASE DE DATOS
-- ============================================================================
IF DATABASE_PRINCIPAL_ID('db_rol_superadmin') IS NULL
    CREATE ROLE [db_rol_superadmin] AUTHORIZATION [dbo];
GO
IF DATABASE_PRINCIPAL_ID('db_rol_gerencia') IS NULL
    CREATE ROLE [db_rol_gerencia] AUTHORIZATION [dbo];
GO
IF DATABASE_PRINCIPAL_ID('db_rol_cajero_pos') IS NULL
    CREATE ROLE [db_rol_cajero_pos] AUTHORIZATION [dbo];
GO
IF DATABASE_PRINCIPAL_ID('db_rol_produccion') IS NULL
    CREATE ROLE [db_rol_produccion] AUTHORIZATION [dbo];
GO
IF DATABASE_PRINCIPAL_ID('db_rol_kiosco') IS NULL
    CREATE ROLE [db_rol_kiosco] AUTHORIZATION [dbo];
GO
IF DATABASE_PRINCIPAL_ID('db_rol_portal_cliente') IS NULL
    CREATE ROLE [db_rol_portal_cliente] AUTHORIZATION [dbo];
GO

-- ============================================================================
-- 2. USUARIOS CONTENIDOS DE BASE DE DATOS (PARA AISLAMIENTO Y EXECUTE AS USER)
-- ============================================================================
IF DATABASE_PRINCIPAL_ID('usr_bd_superadmin') IS NULL
    CREATE USER [usr_bd_superadmin] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [seguridad];
ALTER ROLE [db_rol_superadmin] ADD MEMBER [usr_bd_superadmin];
GO

IF DATABASE_PRINCIPAL_ID('usr_bd_gerencia') IS NULL
    CREATE USER [usr_bd_gerencia] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [ventas];
ALTER ROLE [db_rol_gerencia] ADD MEMBER [usr_bd_gerencia];
GO

IF DATABASE_PRINCIPAL_ID('usr_bd_cajero_pos') IS NULL
    CREATE USER [usr_bd_cajero_pos] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [ventas];
ALTER ROLE [db_rol_cajero_pos] ADD MEMBER [usr_bd_cajero_pos];
GO

IF DATABASE_PRINCIPAL_ID('usr_bd_produccion') IS NULL
    CREATE USER [usr_bd_produccion] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [produccion];
ALTER ROLE [db_rol_produccion] ADD MEMBER [usr_bd_produccion];
GO

IF DATABASE_PRINCIPAL_ID('usr_bd_kiosco') IS NULL
    CREATE USER [usr_bd_kiosco] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [rrhh];
ALTER ROLE [db_rol_kiosco] ADD MEMBER [usr_bd_kiosco];
GO

IF DATABASE_PRINCIPAL_ID('usr_bd_portal_cliente') IS NULL
    CREATE USER [usr_bd_portal_cliente] WITHOUT LOGIN WITH DEFAULT_SCHEMA = [catalogo];
ALTER ROLE [db_rol_portal_cliente] ADD MEMBER [usr_bd_portal_cliente];
GO

-- ============================================================================
-- 2.1 SINCRONIZACIÓN DEL CATÁLOGO DE ROLES DE APLICACIÓN ([seguridad].[Roles])
--     Asegura que los 6 roles documentados en la arquitectura existan en la
--     tabla de seguridad y estén alineados con sus roles nativos de SQL Server.
-- ============================================================================
IF OBJECT_ID('seguridad.Roles', 'U') IS NOT NULL
BEGIN
    DECLARE @CatalogoRoles TABLE (
        Nombre VARCHAR(50),
        Descripcion VARCHAR(200)
    );

    INSERT INTO @CatalogoRoles (Nombre, Descripcion) VALUES
        ('SuperAdmin', 'Administrador General y Auditoría Técnica (db_rol_superadmin): Control total de 8 esquemas, auditoría forense y bitácora SMTP'),
        ('Admin',      'Gerencia y Administración (db_rol_gerencia): Dashboard, Contabilidad, Planilla/RRHH, Fiscal DGI, Arqueos y Usuarios'),
        ('Estandar',   'Cajero POS y Atención (db_rol_cajero_pos): Punto de Venta, Turnos, Facturación, Cotizaciones, Monitor y Arqueo Etapa 1'),
        ('Invitado',   'Portal Cliente / Consulta (db_rol_portal_cliente): Catálogo público, solicitud de cotizaciones propias y seguimiento'),
        ('Operativo',  'Producción, Cocina y Bodega (db_rol_produccion): Monitor KDS, Producción, Recetas, Inventario de Materia Prima y Mermas'),
        ('Kiosco',     'Terminal Biométrica de Asistencia (db_rol_kiosco): Kiosco de reconocimiento facial SFace y marcaje de entrada/salida');

    UPDATE r
    SET r.Descripcion = c.Descripcion
    FROM [seguridad].[Roles] r
    INNER JOIN @CatalogoRoles c ON r.Nombre = c.Nombre;

    INSERT INTO [seguridad].[Roles] (Nombre, Descripcion)
    SELECT c.Nombre, c.Descripcion
    FROM @CatalogoRoles c
    WHERE NOT EXISTS (
        SELECT 1 FROM [seguridad].[Roles] r WHERE r.Nombre = c.Nombre
    );
END
GO

-- ============================================================================
-- 3. DYNAMIC DATA MASKING (DDM) EN COLUMNAS SENSIBLES
-- ============================================================================
BEGIN TRY
    IF OBJECT_ID('seguridad.Usuarios', 'U') IS NOT NULL
       AND COL_LENGTH('seguridad.Usuarios', 'TOTPSecret') IS NOT NULL
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM sys.masked_columns
            WHERE object_id = OBJECT_ID('seguridad.Usuarios') AND name = 'TOTPSecret'
        )
            EXEC('ALTER TABLE [seguridad].[Usuarios] ALTER COLUMN [TOTPSecret] ADD MASKED WITH (FUNCTION = ''default()'')');
    END

    IF OBJECT_ID('rrhh.Empleados', 'U') IS NOT NULL
       AND COL_LENGTH('rrhh.Empleados', 'Cedula') IS NOT NULL
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM sys.masked_columns
            WHERE object_id = OBJECT_ID('rrhh.Empleados') AND name = 'Cedula'
        )
            EXEC('ALTER TABLE [rrhh].[Empleados] ALTER COLUMN [Cedula] ADD MASKED WITH (FUNCTION = ''partial(3,"XXXXXXX",4)'')');
    END

    IF OBJECT_ID('rrhh.Empleados', 'U') IS NOT NULL
       AND COL_LENGTH('rrhh.Empleados', 'NumeroINSS') IS NOT NULL
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM sys.masked_columns
            WHERE object_id = OBJECT_ID('rrhh.Empleados') AND name = 'NumeroINSS'
        )
            EXEC('ALTER TABLE [rrhh].[Empleados] ALTER COLUMN [NumeroINSS] ADD MASKED WITH (FUNCTION = ''partial(2,"XXXX",2)'')');
    END

    IF OBJECT_ID('rrhh.Empleados', 'U') IS NOT NULL
       AND COL_LENGTH('rrhh.Empleados', 'FaceDescriptor') IS NOT NULL
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM sys.masked_columns
            WHERE object_id = OBJECT_ID('rrhh.Empleados') AND name = 'FaceDescriptor'
        )
            EXEC('ALTER TABLE [rrhh].[Empleados] ALTER COLUMN [FaceDescriptor] ADD MASKED WITH (FUNCTION = ''default()'')');
    END
END TRY
BEGIN CATCH
    -- En caso de ediciones de SQL Server sin soporte de DDM, continuar sin abortar lote
END CATCH
GO

BEGIN TRY
    GRANT UNMASK TO [db_rol_superadmin];
    GRANT UNMASK TO [db_rol_gerencia];
    GRANT UNMASK TO [db_rol_kiosco];
END TRY
BEGIN CATCH
END CATCH
GO

-- Permitir visibilidad de metadatos de catálogo (sys.procedures, sys.synonyms, OBJECT_ID)
-- sin otorgar ningún permiso SELECT/INSERT/UPDATE/DELETE sobre datos de tablas.
GRANT VIEW DEFINITION TO [db_rol_superadmin];
GRANT VIEW DEFINITION TO [db_rol_gerencia];
GRANT VIEW DEFINITION TO [db_rol_cajero_pos];
GRANT VIEW DEFINITION TO [db_rol_produccion];
GRANT VIEW DEFINITION TO [db_rol_kiosco];
GRANT VIEW DEFINITION TO [db_rol_portal_cliente];
GO

-- ============================================================================
-- 4. DENEGACIÓN ESTRICTA DE ACCESO DIRECTO A TABLAS Y SINÓNIMOS (DML DIRECTO)
--    Los roles operativos NO pueden ejecutar SELECT/INSERT/UPDATE/DELETE directo
--    sobre tablas ni sinónimos; solo pueden invocar Stored Procedures autorizados.
-- ============================================================================
DECLARE @RolesOperativos TABLE (NombreRol SYSNAME);
INSERT INTO @RolesOperativos VALUES
('db_rol_gerencia'),
('db_rol_cajero_pos'),
('db_rol_produccion'),
('db_rol_kiosco'),
('db_rol_portal_cliente');

DECLARE @EsquemasDominio TABLE (NombreEsquema SYSNAME);
INSERT INTO @EsquemasDominio VALUES
('seguridad'), ('crm'), ('catalogo'), ('ventas'),
('produccion'), ('rrhh'), ('contabilidad'), ('fiscal'), ('dbo');

DECLARE @Rol SYSNAME, @Esq SYSNAME, @CmdDeny NVARCHAR(MAX);

DECLARE cur_deny CURSOR LOCAL FAST_FORWARD FOR
    SELECT r.NombreRol, e.NombreEsquema
    FROM @RolesOperativos r
    CROSS JOIN @EsquemasDominio e;

OPEN cur_deny;
FETCH NEXT FROM cur_deny INTO @Rol, @Esq;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @CmdDeny = N'DENY SELECT, INSERT, UPDATE, DELETE ON SCHEMA::[' + @Esq + N'] TO [' + @Rol + N'];';
    EXEC sp_executesql @CmdDeny;
    FETCH NEXT FROM cur_deny INTO @Rol, @Esq;
END

CLOSE cur_deny;
DEALLOCATE cur_deny;
GO

-- SuperAdmin tampoco debe poder hacer DELETE directo sobre esquemas contables, fiscales o auditoría
DENY DELETE ON SCHEMA::[fiscal] TO [db_rol_superadmin];
DENY DELETE ON SCHEMA::[contabilidad] TO [db_rol_superadmin];
IF OBJECT_ID('seguridad.AuditLog', 'U') IS NOT NULL
    DENY DELETE, UPDATE ON OBJECT::[seguridad].[AuditLog] TO [db_rol_superadmin];
IF OBJECT_ID('seguridad.BitacoraErrores', 'U') IS NOT NULL
    DENY DELETE ON OBJECT::[seguridad].[BitacoraErrores] TO [db_rol_superadmin];
GO



-- ============================================================================
-- Rol Nativo: db_rol_alertas_worker (Worker de Background para Alertas SMTP)
-- ============================================================================
IF DATABASE_PRINCIPAL_ID(N'db_rol_alertas_worker') IS NULL
BEGIN
    CREATE ROLE [db_rol_alertas_worker] AUTHORIZATION [dbo];
END
GO

-- Denegar acceso directo a tablas base al rol worker
DENY SELECT, INSERT, UPDATE, DELETE ON SCHEMA::seguridad TO [db_rol_alertas_worker];
GO

-- Permisos exclusivos de ejecución sobre SPs de Alertas
GRANT EXECUTE ON OBJECT::seguridad.sp_EncolarAlertaSMTP TO [db_rol_alertas_worker];
GRANT EXECUTE ON OBJECT::seguridad.sp_ReclamarAlertaSMTP TO [db_rol_alertas_worker];
GRANT EXECUTE ON OBJECT::seguridad.sp_FinalizarAlertaSMTP TO [db_rol_alertas_worker];
GO


-- ============================================================================
-- 9. PROCEDIMIENTOS ALMACENADOS (CATÁLOGO COMPLETO EMPRESARIAL - 356+ SPS)
-- ============================================================================
/* ============================================================================
   PANADERÍA Y REPOSTERÍA BRAJHER'S CAKE (PANADERÍA AMADA)
   ARCHIVO: 03_stored_procedures.sql
   PROPÓSITO:
     1. Catálogo integral de Procedimientos Almacenados (sp_...) separados en
        los 8 esquemas de dominio (seguridad, catalogo, crm, ventas, produccion,
        rrhh, contabilidad, fiscal).
     2. Manejo estructurado de errores (BEGIN TRY ... BEGIN CATCH) con registro
        automático en [seguridad].[BitacoraErrores] mediante [seguridad].[sp_RegistrarErrorBD]
        y soporte opcional para Database Mail (msdb.dbo.sp_send_dbmail).
     3. Asignación granular de permisos (GRANT EXECUTE / DENY EXECUTE) a los
        6 roles de base de datos (Ownership Chaining).
   ============================================================================ */

SET NOCOUNT ON;
GO

-- ============================================================================
-- 1. ESQUEMA [seguridad]: BITÁCORA DE ERRORES, BLOQUEOS, USUARIOS Y AUDITORÍA
-- ============================================================================

CREATE OR ALTER PROCEDURE [seguridad].[sp_RegistrarErrorBD]
    @Origen VARCHAR(30) = 'SQL_SP',
    @Severidad VARCHAR(15) = 'ERROR',
    @NumeroError INT = NULL,
    @EstadoError INT = NULL,
    @LineaError INT = NULL,
    @Procedimiento NVARCHAR(128) = NULL,
    @EsquemaOrigen NVARCHAR(64) = NULL,
    @MensajeError NVARCHAR(2000) = NULL,
    @DetalleTecnico NVARCHAR(MAX) = NULL,
    @ParametrosJSON NVARCHAR(MAX) = NULL,
    @UsuarioID INT = NULL,
    @Username NVARCHAR(100) = NULL,
    @RolAplicacion NVARCHAR(50) = NULL,
    @DireccionIP VARCHAR(45) = NULL,
    @RutaHTTP NVARCHAR(255) = NULL,
    @ErrorRegistradoID BIGINT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    -- Capturar datos del bloque CATCH actual si no fueron suministrados explícitamente
    SET @NumeroError = ISNULL(@NumeroError, ERROR_NUMBER());
    SET @EstadoError = ISNULL(@EstadoError, ERROR_STATE());
    SET @LineaError = ISNULL(@LineaError, ERROR_LINE());
    SET @Procedimiento = ISNULL(@Procedimiento, ERROR_PROCEDURE());
    SET @MensajeError = ISNULL(@MensajeError, ISNULL(ERROR_MESSAGE(), N'Error SQL no especificado'));

    IF @Severidad NOT IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
        SET @Severidad = 'ERROR';

    -- Leer contexto de sesión inyectado por Flask (SESSION_CONTEXT) si no se pasó por parámetro
    IF @UsuarioID IS NULL
        SET @UsuarioID = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    IF @Username IS NULL
        SET @Username = TRY_CAST(SESSION_CONTEXT(N'username') AS NVARCHAR(100));
    IF @RolAplicacion IS NULL
        SET @RolAplicacion = TRY_CAST(SESSION_CONTEXT(N'rol') AS NVARCHAR(50));
    IF @DireccionIP IS NULL
        SET @DireccionIP = TRY_CAST(SESSION_CONTEXT(N'ip') AS VARCHAR(45));
    IF @RutaHTTP IS NULL
        SET @RutaHTTP = TRY_CAST(SESSION_CONTEXT(N'ruta_http') AS NVARCHAR(255));

    IF @EsquemaOrigen IS NULL AND @Procedimiento IS NOT NULL AND CHARINDEX('.', @Procedimiento) > 0
        SET @EsquemaOrigen = LEFT(@Procedimiento, CHARINDEX('.', @Procedimiento) - 1);

    -- Si no hay transacción condenada (XACT_STATE() <> -1), persistimos el error inmediatamente
    IF XACT_STATE() <> -1
    BEGIN
        INSERT INTO [seguridad].[BitacoraErrores] (
            Origen, Severidad, NumeroError, EstadoError, LineaError,
            Procedimiento, EsquemaOrigen, MensajeError, DetalleTecnico, ParametrosJSON,
            UsuarioID, Username, RolAplicacion, UsuarioBD, DireccionIP, RutaHTTP
        )
        VALUES (
            ISNULL(@Origen, 'SQL_SP'),
            @Severidad,
            @NumeroError,
            @EstadoError,
            @LineaError,
            @Procedimiento,
            @EsquemaOrigen,
            LEFT(@MensajeError, 2000),
            @DetalleTecnico,
            @ParametrosJSON,
            @UsuarioID,
            @Username,
            @RolAplicacion,
            ORIGINAL_LOGIN(),
            @DireccionIP,
            @RutaHTTP
        );

        SET @ErrorRegistradoID = SCOPE_IDENTITY();

        -- Envío opcional por Database Mail nativo de SQL Server si está configurado
        BEGIN TRY
            DECLARE @PerfilDBMail NVARCHAR(128), @DestinatarioDBMail NVARCHAR(255);
            SELECT @PerfilDBMail = Valor FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'dbmail_profile_name';
            SELECT @DestinatarioDBMail = Valor FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_destinatario_alertas';

            IF @PerfilDBMail IS NOT NULL AND LEN(LTRIM(RTRIM(@PerfilDBMail))) > 0
               AND @DestinatarioDBMail IS NOT NULL AND LEN(LTRIM(RTRIM(@DestinatarioDBMail))) > 0
               AND OBJECT_ID('msdb.dbo.sp_send_dbmail') IS NOT NULL
            BEGIN
                DECLARE @AsuntoMail NVARCHAR(255) = CONCAT(N'[ALERTA BD - ', @Severidad, N'] ', ISNULL(@Procedimiento, @Origen));
                DECLARE @CuerpoMail NVARCHAR(MAX) = CONCAT(
                    N'Error registrado en PanaderiaDB (#', @ErrorRegistradoID, N')', CHAR(13)+CHAR(10),
                    N'Severidad: ', @Severidad, CHAR(13)+CHAR(10),
                    N'Origen/Procedimiento: ', ISNULL(@Procedimiento, @Origen), CHAR(13)+CHAR(10),
                    N'Número/Línea: ', ISNULL(CAST(@NumeroError AS VARCHAR(20)), 'N/A'), N' / L', ISNULL(CAST(@LineaError AS VARCHAR(20)), 'N/A'), CHAR(13)+CHAR(10),
                    N'Usuario App / Rol: ', ISNULL(@Username, 'Anónimo'), N' (', ISNULL(@RolAplicacion, 'N/A'), N')', CHAR(13)+CHAR(10),
                    N'IP / Ruta: ', ISNULL(@DireccionIP, 'N/A'), N' ', ISNULL(@RutaHTTP, ''), CHAR(13)+CHAR(10),
                    N'Mensaje: ', @MensajeError
                );
                DECLARE @CmdDBMail NVARCHAR(200) = N'msdb.dbo.sp_send_dbmail';

                EXEC @CmdDBMail
                    @profile_name = @PerfilDBMail,
                    @recipients = @DestinatarioDBMail,
                    @subject = @AsuntoMail,
                    @body = @CuerpoMail;

                UPDATE [seguridad].[BitacoraErrores]
                SET NotificadoSMTP = 1, FechaNotificacion = SYSDATETIME()
                WHERE ID = @ErrorRegistradoID;
            END
        END TRY
        BEGIN CATCH
            -- No interrumpir el registro local si Database Mail no está habilitado en la instancia
        END CATCH
    END
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_MarcarErrorNotificadoSMTP]
    @ErrorID BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [seguridad].[BitacoraErrores]
    SET NotificadoSMTP = 1,
        FechaNotificacion = SYSDATETIME()
    WHERE ID = @ErrorID;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarBitacoraErrores]
    @Top INT = 200,
    @Severidad VARCHAR(15) = NULL,
    @Origen VARCHAR(30) = NULL,
    @SoloNoNotificados BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@Top)
        ID, FechaHora, Origen, Severidad, NumeroError, EstadoError, LineaError,
        Procedimiento, EsquemaOrigen, MensajeError, DetalleTecnico, ParametrosJSON,
        UsuarioID, Username, RolAplicacion, UsuarioBD, DireccionIP, RutaHTTP,
        NotificadoSMTP, FechaNotificacion
    FROM [seguridad].[BitacoraErrores]
    WHERE (@Severidad IS NULL OR Severidad = @Severidad)
      AND (@Origen IS NULL OR Origen = @Origen)
      AND (@SoloNoNotificados = 0 OR NotificadoSMTP = 0)
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_RegistrarIntentoLogin]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45),
    @Exitoso BIT,
    @MaxIntentos INT = 5,
    @MinutosBloqueo INT = 15
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Ahora DATETIME2 = SYSDATETIME();
    DECLARE @IntentosActuales INT = 0;
    DECLARE @BloqueadoHasta DATETIME2 = NULL;
    DECLARE @EstaBloqueado BIT = 0;
    DECLARE @RecienBloqueado BIT = 0;

    BEGIN TRY
        SET @Identificador = LTRIM(RTRIM(ISNULL(@Identificador, N'desconocido')));
        SET @DireccionIP = LTRIM(RTRIM(ISNULL(@DireccionIP, '0.0.0.0')));

        -- Leer configuración dinámica si existe
        SELECT @MaxIntentos = ISNULL(TRY_CAST(Valor AS INT), @MaxIntentos)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_intentos_max';

        SELECT @MinutosBloqueo = ISNULL(TRY_CAST(Valor AS INT), @MinutosBloqueo)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_minutos';

        IF @Exitoso = 1
        BEGIN
            DELETE FROM [seguridad].[BloqueosCuenta]
            WHERE Identificador = @Identificador AND DireccionIP = @DireccionIP;

            SELECT
                CAST(0 AS BIT) AS Bloqueado,
                CAST(0 AS BIT) AS RecienBloqueado,
                0 AS IntentosFallidos,
                CAST(NULL AS DATETIME2) AS BloqueadoHasta;
            RETURN;
        END

        -- Verificar si ya existe registro para (Identificador, IP)
        SELECT @IntentosActuales = IntentosFallidos, @BloqueadoHasta = BloqueadoHasta
        FROM [seguridad].[BloqueosCuenta] WITH (UPDLOCK, HOLDLOCK)
        WHERE Identificador = @Identificador AND DireccionIP = @DireccionIP;

        IF @@ROWCOUNT = 0
        BEGIN
            SET @IntentosActuales = 1;
            IF @IntentosActuales >= @MaxIntentos
            BEGIN
                SET @BloqueadoHasta = DATEADD(MINUTE, @MinutosBloqueo, @Ahora);
                SET @EstaBloqueado = 1;
                SET @RecienBloqueado = 1;
            END

            INSERT INTO [seguridad].[BloqueosCuenta] (
                Identificador, DireccionIP, IntentosFallidos, PrimerIntento, UltimoIntento, BloqueadoHasta, Motivo
            )
            VALUES (
                @Identificador, @DireccionIP, @IntentosActuales, @Ahora, @Ahora, @BloqueadoHasta,
                CASE WHEN @EstaBloqueado = 1 THEN N'Exceso de intentos fallidos de inicio de sesión' ELSE NULL END
            );
        END
        ELSE
        BEGIN
            -- Si el bloqueo anterior ya expiró hace más de 15 minutos, reiniciar contador
            IF @BloqueadoHasta IS NOT NULL AND @BloqueadoHasta < @Ahora
            BEGIN
                SET @IntentosActuales = 1;
                SET @BloqueadoHasta = NULL;
            END
            ELSE
            BEGIN
                SET @IntentosActuales = @IntentosActuales + 1;
            END

            IF @IntentosActuales >= @MaxIntentos
            BEGIN
                IF @BloqueadoHasta IS NULL OR @BloqueadoHasta < @Ahora
                    SET @RecienBloqueado = 1;
                SET @BloqueadoHasta = DATEADD(MINUTE, @MinutosBloqueo, @Ahora);
                SET @EstaBloqueado = 1;
            END

            UPDATE [seguridad].[BloqueosCuenta]
            SET IntentosFallidos = @IntentosActuales,
                UltimoIntento = @Ahora,
                BloqueadoHasta = @BloqueadoHasta,
                Motivo = CASE WHEN @EstaBloqueado = 1 THEN N'Exceso de intentos fallidos de inicio de sesión' ELSE Motivo END
            WHERE Identificador = @Identificador AND DireccionIP = @DireccionIP;
        END

        IF @RecienBloqueado = 1
        BEGIN
            DECLARE @MsgBloqueo NVARCHAR(500) = CONCAT(
                N'Cuenta bloqueada temporalmente por fuerza bruta: identificador "', @Identificador,
                N'" desde IP ', @DireccionIP, N' tras ', @IntentosActuales, N' intentos fallidos.'
            );
            EXEC [seguridad].[sp_RegistrarErrorBD]
                @Origen = 'SEGURIDAD_AUTH',
                @Severidad = 'CRITICAL',
                @NumeroError = 50401,
                @EstadoError = 1,
                @LineaError = 1,
                @Procedimiento = N'seguridad.sp_RegistrarIntentoLogin',
                @EsquemaOrigen = N'seguridad',
                @MensajeError = @MsgBloqueo,
                @Username = @Identificador,
                @DireccionIP = @DireccionIP,
                @RutaHTTP = N'/login';
        END

        SELECT
            @EstaBloqueado AS Bloqueado,
            @RecienBloqueado AS RecienBloqueado,
            @IntentosActuales AS IntentosFallidos,
            @BloqueadoHasta AS BloqueadoHasta;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_RegistrarIntentoLogin';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_VerificarBloqueoCuenta]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Ahora DATETIME2 = SYSDATETIME();
    SELECT TOP 1
        ID,
        Identificador,
        DireccionIP,
        IntentosFallidos,
        BloqueadoHasta,
        CASE WHEN BloqueadoHasta IS NOT NULL AND BloqueadoHasta > @Ahora THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS EstaBloqueado
    FROM [seguridad].[BloqueosCuenta]
    WHERE Identificador = @Identificador
      AND DireccionIP = @DireccionIP
      AND BloqueadoHasta > @Ahora;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerUsuarioPorID]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        u.ID, u.Username, u.NombreCompleto, u.RolID, r.Nombre AS RolNombre,
        u.TOTPSecret, u.TOTPEnabled
    FROM [seguridad].[Usuarios] u
    JOIN [seguridad].[Roles] r ON u.RolID = r.ID
    WHERE u.ID = @UsuarioID AND u.Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_AutenticarUsuario]
    @Username NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        u.ID, u.Username, u.PasswordHash, u.NombreCompleto, u.RolID, r.Nombre AS RolNombre,
        u.TOTPSecret, u.TOTPEnabled
    FROM [seguridad].[Usuarios] u
    JOIN [seguridad].[Roles] r ON u.RolID = r.ID
    WHERE u.Username = @Username AND u.Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarUsuariosYRoles]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        u.ID, u.NombreCompleto, u.Username,
        r.Nombre AS Rol, u.Activo, u.RolID, u.TOTPEnabled
    FROM [seguridad].[Usuarios] u
    JOIN [seguridad].[Roles] r ON u.RolID = r.ID
    ORDER BY u.NombreCompleto;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarRoles]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Descripcion FROM [seguridad].[Roles] ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_CrearUsuario]
    @NombreCompleto NVARCHAR(100),
    @Username NVARCHAR(50),
    @PasswordHash NVARCHAR(255),
    @RolID INT,
    @ActorID INT = NULL,
    @DireccionIP VARCHAR(45) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @RolNombre NVARCHAR(50);
        SELECT @RolNombre = Nombre FROM [seguridad].[Roles] WHERE ID = @RolID;
        IF @RolNombre IS NULL
            THROW 52001, 'El rol especificado no existe.', 1;

        INSERT INTO [seguridad].[Usuarios] (NombreCompleto, Username, PasswordHash, RolID, Activo)
        OUTPUT INSERTED.ID, @RolNombre AS RolNombre
        VALUES (@NombreCompleto, @Username, @PasswordHash, @RolID, 1);
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_CrearUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_CambiarEstadoUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [seguridad].[Usuarios]
        SET Activo = 1 ^ Activo
        OUTPUT DELETED.NombreCompleto, DELETED.Username, DELETED.RolID, DELETED.Activo AS ActivoAntes, INSERTED.Activo AS ActivoDespues
        WHERE ID = @UsuarioID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_CambiarEstadoUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_RestablecerTOTPUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [seguridad].[Usuarios]
        SET TOTPSecret = NULL, TOTPEnabled = 0
        WHERE ID = @UsuarioID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_RestablecerTOTPUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerConfiguracionSistema]
    @Prefijo NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Clave, Valor, Descripcion
    FROM [seguridad].[ConfiguracionSistema]
    WHERE (@Prefijo IS NULL OR Clave LIKE @Prefijo + '%')
    ORDER BY Clave;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_GuardarConfiguracionSistema]
    @Clave NVARCHAR(100),
    @Valor NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [seguridad].[ConfiguracionSistema]
        SET Valor = @Valor
        WHERE Clave = @Clave;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_GuardarConfiguracionSistema';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_RegistrarAuditoria]
    @UsuarioID INT = NULL,
    @Accion VARCHAR(50),
    @Entidad VARCHAR(50),
    @EntidadID INT = NULL,
    @DatosAntes NVARCHAR(MAX) = NULL,
    @DatosDespues NVARCHAR(MAX) = NULL,
    @IP VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [seguridad].[AuditLog] (UsuarioID, Accion, Entidad, EntidadID, DatosAntes, DatosDespues, IP)
    VALUES (@UsuarioID, @Accion, @Entidad, @EntidadID, @DatosAntes, @DatosDespues, @IP);
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarAuditoria]
    @Desde DATETIME = NULL,
    @Hasta DATETIME = NULL,
    @Entidad VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 500
        a.ID, a.FechaHora, a.Accion, a.Entidad, a.EntidadID,
        a.DatosAntes, a.DatosDespues, a.IP, u.NombreCompleto
    FROM [seguridad].[AuditLog] a
    LEFT JOIN [seguridad].[Usuarios] u ON u.ID = a.UsuarioID
    WHERE (@Desde IS NULL OR a.FechaHora >= @Desde)
      AND (@Hasta IS NULL OR a.FechaHora < DATEADD(DAY, 1, @Hasta))
      AND (@Entidad IS NULL OR a.Entidad = @Entidad)
    ORDER BY a.FechaHora DESC;
END
GO

-- ============================================================================
-- 2. ESQUEMA [catalogo]: CATEGORÍAS, PRODUCTOS E INGREDIENTES
-- ============================================================================

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerCatalogoActivo]
    @Seccion VARCHAR(20) = 'PRODUCTOS' -- 'CATEGORIAS', 'PRODUCTOS', 'INGREDIENTES'
AS
BEGIN
    SET NOCOUNT ON;
    IF @Seccion = 'CATEGORIAS'
    BEGIN
        SELECT DISTINCT c.ID, c.Nombre
        FROM [catalogo].[Categorias] c
        JOIN [catalogo].[Productos] p ON p.CategoriaID = c.ID
        WHERE p.Activo = 1
        ORDER BY c.Nombre;
    END
    ELSE IF @Seccion = 'INGREDIENTES'
    BEGIN
        SELECT ID, Nombre, PrecioAdicional
        FROM [catalogo].[Ingredientes]
        WHERE Activo = 1
        ORDER BY Nombre;
    END
    ELSE
    BEGIN
        SELECT
            p.ID, p.CategoriaID, p.Nombre, c.Nombre AS Categoria,
            p.PrecioBase, p.EsFicticio, p.PorcentajeDescuento, p.ImagenUrl, p.TasaIVA
        FROM [catalogo].[Productos] p
        JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
        WHERE p.Activo = 1
        ORDER BY c.Nombre, p.Nombre;
    END
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ListarProductosAdmin]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.ID, p.Nombre, c.Nombre AS Categoria, p.CategoriaID,
        p.PrecioBase, p.Activo, p.EsFicticio,
        p.PorcentajeDescuento, p.ImagenUrl,
        p.TasaIVA, p.MotivoExencion
    FROM [catalogo].[Productos] p
    JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
    ORDER BY c.Nombre, p.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_GuardarProducto]
    @ProductoID INT = NULL,
    @CategoriaID INT,
    @Nombre NVARCHAR(100),
    @PrecioBase DECIMAL(10,2),
    @PorcentajeDescuento DECIMAL(5,2) = 0.00,
    @ImagenUrl VARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF @PrecioBase <= 0
            THROW 52010, 'El precio base debe ser mayor a cero.', 1;

        IF @ProductoID IS NULL
        BEGIN
            INSERT INTO [catalogo].[Productos] (
                CategoriaID, Nombre, PrecioBase, PorcentajeDescuento, ImagenUrl, Activo, EsFicticio
            )
            OUTPUT INSERTED.ID
            VALUES (@CategoriaID, @Nombre, @PrecioBase, @PorcentajeDescuento, @ImagenUrl, 1, 0);
        END
        ELSE
        BEGIN
            UPDATE [catalogo].[Productos]
            SET CategoriaID = @CategoriaID,
                Nombre = @Nombre,
                PrecioBase = @PrecioBase,
                PorcentajeDescuento = @PorcentajeDescuento,
                ImagenUrl = ISNULL(@ImagenUrl, ImagenUrl)
            WHERE ID = @ProductoID;

            SELECT @ProductoID AS ID;
        END
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'catalogo.sp_GuardarProducto';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_CambiarEstadoProducto]
    @ProductoID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [catalogo].[Productos]
        SET Activo = 1 ^ Activo
        OUTPUT DELETED.Nombre, DELETED.PrecioBase, DELETED.CategoriaID, DELETED.Activo AS ActivoAntes, INSERTED.Activo AS ActivoDespues
        WHERE ID = @ProductoID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'catalogo.sp_CambiarEstadoProducto';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ActualizarTratamientoIVAProducto]
    @ProductoID INT,
    @TasaIVA DECIMAL(5,2),
    @MotivoExencion NVARCHAR(200) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [catalogo].[Productos]
        SET TasaIVA = @TasaIVA,
            MotivoExencion = @MotivoExencion
        WHERE ID = @ProductoID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'catalogo.sp_ActualizarTratamientoIVAProducto';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 3. ESQUEMA [crm]: CLIENTES, FIDELIZACIÓN Y COTIZACIONES
-- ============================================================================

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerClientePorID]
    @ClienteID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Apellidos, Telefono, EsInvitado, NivelConfianzaID, FechaNacimiento, RutaFotoPerfil
    FROM [crm].[Clientes]
    WHERE ID = @ClienteID;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerClientePorTelefono]
    @Telefono VARCHAR(30)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Apellidos, Telefono, PasswordHash, EsInvitado, NivelConfianzaID, FechaNacimiento, RutaFotoPerfil
    FROM [crm].[Clientes]
    WHERE Telefono = @Telefono
    ORDER BY EsInvitado ASC, ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_CrearInvitadoTemporal]
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        INSERT INTO [crm].[Clientes] (Nombre, EsInvitado, NivelConfianzaID, TotalCompras)
        OUTPUT INSERTED.ID
        VALUES ('Invitado Temporal', 1, 1, 0);
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_CrearInvitadoTemporal';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ListarClientesFidelizacion]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre AS Nivel,
        ISNULL(SUM(f.Total), 0) AS TotalGastado, MAX(f.FechaHora) AS UltimaCompra
    FROM [crm].[Clientes] c
    JOIN [crm].[NivelesConfianza] nc ON c.NivelConfianzaID = nc.ID
    LEFT JOIN [ventas].[Facturas] f ON f.ClienteID = c.ID AND f.EstadoFiscal = 'Emitida'
    WHERE c.ID > 1
    GROUP BY c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre
    ORDER BY c.TotalCompras DESC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerExpedienteCliente]
    @ClienteID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ID, Nombre, Apellidos, Telefono, Genero, FechaNacimiento,
        RutaFotoPerfil, TotalCompras, NivelConfianzaID
    FROM [crm].[Clientes]
    WHERE ID = @ClienteID AND ID > 1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ActualizarCliente]
    @ClienteID INT,
    @Nombre NVARCHAR(100),
    @Apellidos NVARCHAR(100) = NULL,
    @Telefono VARCHAR(30),
    @Genero VARCHAR(20) = NULL,
    @FechaNacimiento DATE = NULL,
    @NivelConfianzaID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF EXISTS (SELECT 1 FROM [crm].[Clientes] WHERE Telefono = @Telefono AND ID <> @ClienteID)
            THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

        IF NOT EXISTS (SELECT 1 FROM [crm].[NivelesConfianza] WHERE ID = @NivelConfianzaID)
            THROW 52021, 'Nivel de fidelidad inexistente.', 1;

        UPDATE [crm].[Clientes]
        SET Nombre = @Nombre,
            Apellidos = @Apellidos,
            Telefono = @Telefono,
            Genero = @Genero,
            FechaNacimiento = @FechaNacimiento,
            NivelConfianzaID = @NivelConfianzaID
        WHERE ID = @ClienteID AND ID > 1;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_ActualizarCliente';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ListarCotizacionesCliente]
    @ClienteID INT = NULL,
    @SessionID VARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
    IF IS_MEMBER('db_rol_portal_cliente') = 1
    BEGIN
        IF @CtxUsuarioID IS NOT NULL AND @ClienteID IS NOT NULL AND @ClienteID <> @CtxUsuarioID
            THROW 52026, 'No autorizado: ClienteID no coincide con la sesión autenticada.', 1;
        IF @CtxSessionID IS NOT NULL AND @SessionID IS NOT NULL AND @SessionID <> @CtxSessionID
            THROW 52026, 'No autorizado: SessionID no coincide con la sesión activa.', 1;
    END

    SELECT
        ID, Especificaciones, FechaEntrega, RutaImagenReferencia,
        Estado, PrecioCotizado, TelefonoContacto, FechaSolicitud
    FROM [crm].[Cotizaciones]
    WHERE (@ClienteID IS NOT NULL AND ClienteID = @ClienteID)
       OR (@SessionID IS NOT NULL AND ClienteID IS NULL AND SessionID = @SessionID)
    ORDER BY FechaSolicitud DESC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_CrearCotizacion]
    @ClienteID INT = NULL,
    @SessionID VARCHAR(100) = NULL,
    @Especificaciones NVARCHAR(MAX),
    @FechaEntrega DATETIME2,
    @RutaImagenReferencia VARCHAR(255) = NULL,
    @TelefonoContacto VARCHAR(30),
    @NombreContacto NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        INSERT INTO [crm].[Cotizaciones] (
            ClienteID, SessionID, Especificaciones, FechaEntrega,
            RutaImagenReferencia, TelefonoContacto, Estado, NombreContacto
        )
        OUTPUT INSERTED.ID
        VALUES (
            @ClienteID, @SessionID, @Especificaciones, @FechaEntrega,
            @RutaImagenReferencia, @TelefonoContacto, 'Pendiente', @NombreContacto
        );
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_CrearCotizacion';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ActualizarEstadoCotizacion]
    @CotizacionID INT,
    @NuevoEstado VARCHAR(30),
    @PrecioCotizado DECIMAL(10,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF IS_MEMBER('db_rol_portal_cliente') = 1
           OR TRY_CAST(SESSION_CONTEXT(N'rol') AS NVARCHAR(50)) IN (N'Cliente', N'Invitado')
            THROW 52025, 'Operación administrativa de cotizaciones no autorizada para el portal de clientes.', 1;

        UPDATE [crm].[Cotizaciones]
        SET Estado = @NuevoEstado,
            PrecioCotizado = ISNULL(@PrecioCotizado, PrecioCotizado)
        WHERE ID = @CotizacionID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_ActualizarEstadoCotizacion';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 4. ESQUEMA [ventas]: DASHBOARD, ESTADÍSTICAS, POS, FACTURAS, ENCARGOS, ARQUEOS
-- ============================================================================

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerDashboardEjecutivo]
    @FechaHoy DATE
AS
BEGIN
    SET NOCOUNT ON;
    -- Resumen principal del día y estado global de encargos
    SELECT
        (SELECT ISNULL(SUM(Total), 0) FROM [ventas].[Facturas] WHERE EstadoFiscal = 'Emitida' AND CONVERT(date, FechaHora) = @FechaHoy) AS VentasHoy,
        (SELECT ISNULL(COUNT(ID), 0) FROM [ventas].[Facturas] WHERE EstadoFiscal = 'Emitida' AND CONVERT(date, FechaHora) = @FechaHoy) AS TotalFacturasHoy,
        (SELECT COUNT(*) FROM [ventas].[Encargos] e JOIN [ventas].[Facturas] f ON e.FacturaID = f.ID
         WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada') AND e.Estado <> 'Entregado') AS EncargosPendientes,
        (SELECT ISNULL(SUM(CASE WHEN e.Estado = 'Listo' THEN 1 ELSE 0 END), 0)
         FROM [ventas].[Encargos] e JOIN [ventas].[Facturas] f ON e.FacturaID = f.ID
         WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada') AND e.Estado <> 'Entregado') AS EncargosListos,
        (SELECT ISNULL(SUM(CASE WHEN CONVERT(date, e.FechaEntrega) < @FechaHoy THEN 1 ELSE 0 END), 0)
         FROM [ventas].[Encargos] e JOIN [ventas].[Facturas] f ON e.FacturaID = f.ID
         WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada') AND e.Estado <> 'Entregado') AS EncargosAtrasados;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerEstadisticasOperativas]
    @Seccion VARCHAR(30) = 'VENTAS_DIARIAS'
AS
BEGIN
    SET NOCOUNT ON;
    IF @Seccion = 'VENTAS_HORA'
    BEGIN
        SELECT DATEPART(HOUR, FechaHora) AS Hora, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM [ventas].[Facturas]
        WHERE EstadoFiscal = 'Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY DATEPART(HOUR, FechaHora)
        ORDER BY Hora;
    END
    ELSE IF @Seccion = 'ROTACION_PRODUCTOS'
    BEGIN
        SELECT TOP 15 p.Nombre, SUM(df.Cantidad) AS Vendidos, SUM(df.Subtotal) AS Ingresos
        FROM [ventas].[DetalleFacturas] df
        JOIN [catalogo].[Productos] p ON df.ProductoID = p.ID
        JOIN [ventas].[Facturas] f ON df.FacturaID = f.ID AND f.EstadoFiscal = 'Emitida'
        WHERE f.FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre
        ORDER BY Vendidos DESC;
    END
    ELSE
    BEGIN
        SELECT CONVERT(date, FechaHora) AS Dia, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM [ventas].[Facturas]
        WHERE EstadoFiscal = 'Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia;
    END
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTurnoActivo]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, FechaApertura
    FROM [ventas].[TurnosCaja]
    WHERE UsuarioID = @UsuarioID AND Cerrado = 0;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_AbrirTurnoCaja]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @TurnoExistenteID INT;
        SELECT @TurnoExistenteID = ID
        FROM [ventas].[TurnosCaja] WITH (UPDLOCK, HOLDLOCK)
        WHERE UsuarioID = @UsuarioID AND Cerrado = 0;

        IF @TurnoExistenteID IS NOT NULL
        BEGIN
            SELECT @TurnoExistenteID AS TurnoID, CAST(0 AS BIT) AS Creado;
            RETURN;
        END

        INSERT INTO [ventas].[TurnosCaja] (UsuarioID, Cerrado)
        OUTPUT INSERTED.ID AS TurnoID, CAST(1 AS BIT) AS Creado
        VALUES (@UsuarioID, 0);
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'ventas.sp_AbrirTurnoCaja';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_SiguienteNumeroFactura]
    @Serie VARCHAR(10) = 'FAC'
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        UPDATE [ventas].[SecuenciasFiscales] WITH (UPDLOCK, HOLDLOCK)
        SET Ultimo = Ultimo + 1
        OUTPUT INSERTED.Ultimo, INSERTED.Serie
        WHERE Serie = @Serie;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'ventas.sp_SiguienteNumeroFactura';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerFacturaImpresion]
    @FacturaID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DocumentoJSON, EstadoFiscal, MotivoAnulacion
    FROM [ventas].[Facturas]
    WHERE ID = @FacturaID;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ConsultarSeguimientoPedido]
    @CodigoSeguimiento VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.ID, f.NumeroFactura, f.CodigoSeguimiento, f.FechaHora,
        f.Subtotal, f.IVA, f.Total, f.EsEncargo, c.Nombre AS ClienteNombre,
        e.FechaEntrega, e.Estado
    FROM [ventas].[Facturas] f
    LEFT JOIN [crm].[Clientes] c ON f.ClienteID = c.ID
    LEFT JOIN [ventas].[Encargos] e ON f.ID = e.FacturaID
    WHERE f.CodigoSeguimiento = @CodigoSeguimiento;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ListarArqueosCaja]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50
        a.ID, a.TurnoID, u_cajero.NombreCompleto AS Cajero,
        ISNULL(u_verif.NombreCompleto, N'—') AS Verificador,
        a.EfectivoContado, a.EfectivoSistema,
        a.TransferenciasContadas, a.TransferenciasSistema,
        a.DiferenciaEfectivo, a.DiferenciaTransferencias,
        a.DolaresContados, a.TipoCambioUsado,
        a.Observaciones, a.NotasDiscrepancia,
        ISNULL(a.EstadoArqueo, 'Cerrado') AS EstadoArqueo,
        a.FechaArqueo, a.FechaVerificacion,
        ISNULL(a.RequiereJustificacion, 0) AS RequiereJustificacion
    FROM [ventas].[ArqueoCaja] a
    JOIN [seguridad].[Usuarios] u_cajero ON a.UsuarioID = u_cajero.ID
    LEFT JOIN [seguridad].[Usuarios] u_verif ON a.VerificadoPorID = u_verif.ID
    ORDER BY a.FechaArqueo DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerDetalleArqueo]
    @ArqueoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TipoMoneda, Denominacion, Cantidad, Subtotal
    FROM [ventas].[ArqueoDetalleDenominacion]
    WHERE ArqueoID = @ArqueoID
    ORDER BY TipoMoneda, Denominacion DESC;
END
GO

-- ============================================================================
-- 5. ESQUEMA [produccion]: MONITOR DE COCINA, INVENTARIO, RECETAS, LOTES, MERMAS
-- ============================================================================

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarEncargosMonitor]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.ID, f.NumeroFactura, f.CodigoSeguimiento, f.FechaHora, f.Total,
        e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones,
        e.RutaImagenReferencia, e.TelefonoContacto,
        c.Nombre AS ClienteNombre, c.Telefono AS ClienteTelefono
    FROM [ventas].[Facturas] f
    JOIN [ventas].[Encargos] e ON e.FacturaID = f.ID
    LEFT JOIN [crm].[Clientes] c ON f.ClienteID = c.ID
    WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada')
      AND e.Estado <> 'Entregado'
    ORDER BY e.FechaEntrega ASC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarInventarioMateriaPrima]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        m.ID, m.Nombre, m.StockActual, m.StockMinimo,
        u.Nombre AS Unidad, u.Abreviatura
    FROM [produccion].[MateriaPrima] m
    JOIN [catalogo].[UnidadesMedida] u ON m.UnidadMedidaID = u.ID
    ORDER BY m.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarProduccionYRecetas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        r.ID, p.Nombre AS Producto, m.Nombre AS Materia,
        r.CantidadNecesaria, u.Abreviatura
    FROM [produccion].[RecetaProducto] r
    JOIN [catalogo].[Productos] p ON r.ProductoID = p.ID
    JOIN [produccion].[MateriaPrima] m ON r.MateriaPrimaID = m.ID
    JOIN [catalogo].[UnidadesMedida] u ON m.UnidadMedidaID = u.ID
    ORDER BY p.Nombre, m.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_GuardarRecetaProducto]
    @ProductoID INT,
    @MateriaPrimaID INT,
    @CantidadNecesaria DECIMAL(10,2)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF @CantidadNecesaria <= 0
            THROW 52030, 'La cantidad necesaria debe ser mayor a cero.', 1;

        IF EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE ProductoID = @ProductoID AND MateriaPrimaID = @MateriaPrimaID)
        BEGIN
            UPDATE [produccion].[RecetaProducto]
            SET CantidadNecesaria = @CantidadNecesaria
            WHERE ProductoID = @ProductoID AND MateriaPrimaID = @MateriaPrimaID;
        END
        ELSE
        BEGIN
            INSERT INTO [produccion].[RecetaProducto] (ProductoID, MateriaPrimaID, CantidadNecesaria)
            VALUES (@ProductoID, @MateriaPrimaID, @CantidadNecesaria);
        END
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_GuardarRecetaProducto';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_EliminarRecetaProducto]
    @RecetaID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DELETE FROM [produccion].[RecetaProducto] WHERE ID = @RecetaID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_EliminarRecetaProducto';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_RegistrarLoteProduccion]
    @ProductoID INT,
    @CantidadProducida INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF @CantidadProducida <= 0
            THROW 52031, 'La cantidad a producir debe ser un entero positivo.', 1;

        IF NOT EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE ProductoID = @ProductoID)
            THROW 52032, 'El producto no tiene receta definida. Imposible producir sin receta.', 1;

        DECLARE @InsumoFaltante NVARCHAR(200);
        SELECT TOP 1
            @InsumoFaltante = CONCAT(
                N'Stock insuficiente de ', m.Nombre,
                N'. Se requieren ', CAST(r.CantidadNecesaria * @CantidadProducida AS NVARCHAR(30)),
                N' y hay ', CAST(m.StockActual AS NVARCHAR(30)), N'.'
            )
        FROM [produccion].[RecetaProducto] r
        JOIN [produccion].[MateriaPrima] m WITH (UPDLOCK, HOLDLOCK) ON r.MateriaPrimaID = m.ID
        WHERE r.ProductoID = @ProductoID
          AND m.StockActual < (r.CantidadNecesaria * @CantidadProducida);

        IF @InsumoFaltante IS NOT NULL
            THROW 52033, @InsumoFaltante, 1;

        DECLARE @LoteID INT;
        INSERT INTO [produccion].[ProduccionLotes] (ProductoID, CantidadProducida)
        VALUES (@ProductoID, @CantidadProducida);
        SET @LoteID = SCOPE_IDENTITY();

        UPDATE m
        SET m.StockActual = m.StockActual - (r.CantidadNecesaria * @CantidadProducida)
        FROM [produccion].[MateriaPrima] m
        JOIN [produccion].[RecetaProducto] r ON r.MateriaPrimaID = m.ID
        WHERE r.ProductoID = @ProductoID;

        INSERT INTO [produccion].[ConsumoLote] (LoteID, MateriaPrimaID, CantidadUsada)
        SELECT @LoteID, r.MateriaPrimaID, (r.CantidadNecesaria * @CantidadProducida)
        FROM [produccion].[RecetaProducto] r
        WHERE r.ProductoID = @ProductoID;

        SELECT @LoteID AS LoteID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_RegistrarLoteProduccion';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_RegistrarMerma]
    @ProductoID INT,
    @Cantidad INT,
    @Motivo VARCHAR(50),
    @Observaciones VARCHAR(255) = NULL,
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        INSERT INTO [produccion].[Mermas] (ProductoID, Cantidad, Motivo, Observaciones, UsuarioID)
        OUTPUT INSERTED.ID
        VALUES (@ProductoID, @Cantidad, @Motivo, @Observaciones, @UsuarioID);
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_RegistrarMerma';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarMermas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        m.ID, p.Nombre AS Producto, m.Cantidad, m.Motivo,
        m.Observaciones, u.NombreCompleto AS RegistradoPor, m.Fecha
    FROM [produccion].[Mermas] m
    JOIN [catalogo].[Productos] p ON m.ProductoID = p.ID
    JOIN [seguridad].[Usuarios] u ON m.UsuarioID = u.ID
    ORDER BY m.Fecha DESC;
END
GO

-- ============================================================================
-- 6. ESQUEMA [rrhh]: EMPLEADOS, KIOSCO BIOMÉTRICO, ASISTENCIA Y NÓMINA
-- ============================================================================

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarPerfilesPuesto]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Cargo, PerfilPuesto, Obligaciones, RequisitosCompetencias, ActualizadoEn
    FROM [rrhh].[PerfilesPuesto] ORDER BY Cargo;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerPerfilPuestoPorCargo]
    @Cargo NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Cargo FROM [rrhh].[PerfilesPuesto] WHERE Cargo=@Cargo;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_GuardarPerfilPuesto]
    @Cargo NVARCHAR(100),
    @PerfilPuesto NVARCHAR(1000),
    @Obligaciones NVARCHAR(2000),
    @RequisitosCompetencias NVARCHAR(1000),
    @ActorID INT,
    @IP VARCHAR(50)=NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET @Cargo=NULLIF(LTRIM(RTRIM(@Cargo)),N'');
    IF @Cargo IS NULL OR NULLIF(LTRIM(RTRIM(@PerfilPuesto)),N'') IS NULL
       OR NULLIF(LTRIM(RTRIM(@Obligaciones)),N'') IS NULL
       OR NULLIF(LTRIM(RTRIM(@RequisitosCompetencias)),N'') IS NULL
       OR @ActorID IS NULL
        THROW 51052, 'Complete el perfil, las obligaciones y las competencias.', 1;
    IF EXISTS(SELECT 1 FROM [rrhh].[PerfilesPuesto] WITH (UPDLOCK,HOLDLOCK) WHERE Cargo=@Cargo)
        UPDATE [rrhh].[PerfilesPuesto]
           SET PerfilPuesto=@PerfilPuesto, Obligaciones=@Obligaciones,
               RequisitosCompetencias=@RequisitosCompetencias,
               ActualizadoEn=SYSUTCDATETIME(), ActualizadoPor=@ActorID
         WHERE Cargo=@Cargo;
    ELSE
        INSERT INTO [rrhh].[PerfilesPuesto](Cargo,PerfilPuesto,Obligaciones,RequisitosCompetencias,ActualizadoPor)
        VALUES(@Cargo,@PerfilPuesto,@Obligaciones,@RequisitosCompetencias,@ActorID);
    EXEC [seguridad].[sp_RegistrarAuditoria] @ActorID, 'PERFIL_PUESTO', 'PerfilPuesto', NULL,
         NULL, @Cargo, @IP;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEmpleadosActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        e.ID, e.NombreCompleto, e.Cedula, e.NumeroINSS, e.Cargo,
        e.TipoContrato, e.TipoJornada, e.FormaPago, e.FechaIngreso,
        e.SalarioBase, e.EstadoEmpleado, e.Telefono, e.ConsentimientoDatos,
        e.HoraEntrada, e.HoraSalida, u.Username
    FROM [rrhh].[Empleados] e
    LEFT JOIN [seguridad].[Usuarios] u ON e.UsuarioID = u.ID
    ORDER BY e.EstadoEmpleado ASC, e.NombreCompleto ASC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerDescriptoresFacialesKiosco]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, FaceDescriptor
    FROM [rrhh].[Empleados]
    WHERE EstadoEmpleado = 'Activo' AND FaceDescriptor IS NOT NULL;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_RegistrarMarcajeKiosco]
    @EmpleadoID INT,
    @Fecha DATE,
    @Hora TIME,
    @EstadoEntrada VARCHAR(20) = 'Puntual',
    @Accion VARCHAR(10) = 'entrada'
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF @Accion = 'entrada'
        BEGIN
            INSERT INTO [rrhh].[Asistencia] (
                EmpleadoID, Fecha, HoraEntrada, EstadoEntrada
            )
            OUTPUT INSERTED.ID
            VALUES (
                @EmpleadoID, @Fecha, @Hora, @EstadoEntrada
            );
        END
        ELSE IF @Accion = 'salida'
        BEGIN
            UPDATE [rrhh].[Asistencia]
            SET HoraSalida = @Hora
            WHERE EmpleadoID = @EmpleadoID AND Fecha = @Fecha;
        END
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'rrhh.sp_RegistrarMarcajeKiosco';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerResumenAsistencia]
    @FechaInicio DATE = NULL,
    @FechaFin DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 200
        a.ID, a.EmpleadoID, e.NombreCompleto, e.Cargo,
        a.Fecha, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada
    FROM [rrhh].[Asistencia] a
    JOIN [rrhh].[Empleados] e ON a.EmpleadoID = e.ID
    WHERE (@FechaInicio IS NULL OR a.Fecha >= @FechaInicio)
      AND (@FechaFin IS NULL OR a.Fecha <= @FechaFin)
    ORDER BY a.Fecha DESC, a.HoraEntrada DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarNominasPeriodo]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        n.ID, n.EmpleadoID, e.NombreCompleto, e.Cargo,
        n.PeriodoInicio, n.PeriodoFin, n.SalarioBruto, n.OtrosIngresos,
        n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto,
        n.INSSPatronal, n.INATEC, n.Estado, n.FechaGeneracion
    FROM [rrhh].[Nomina] n
    JOIN [rrhh].[Empleados] e ON n.EmpleadoID = e.ID
    ORDER BY n.ID DESC;
END
GO

-- ============================================================================
-- 7. ESQUEMA [contabilidad]: PARTIDA DOBLE, ESTADOS FINANCIEROS Y MAYOR
-- ============================================================================

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerCatalogoCuentas]
    @SoloTransaccionales BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ID, Codigo, Nombre, Clase, Grupo, Naturaleza,
        Nivel, CuentaPadreID, EsTransaccional, Activa
    FROM [contabilidad].[CatalogoCuentas]
    WHERE Activa = 1
      AND (@SoloTransaccionales = 0 OR EsTransaccional = 1)
    ORDER BY Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceGeneral]
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;
    WITH SaldosHistoricos AS (
        SELECT
            C.Clase, C.Grupo, C.Codigo, C.Nombre AS Cuenta, C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND A.Fecha < DATEADD(DAY, 1, @FechaCorte)
        GROUP BY C.Clase, C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase, Grupo, Codigo, Cuenta,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (TotalDebe - TotalHaber)
            ELSE (TotalHaber - TotalDebe)
        END AS SaldoFinal
    FROM SaldosHistoricos
    WHERE (TotalDebe - TotalHaber) <> 0
    ORDER BY Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerEstadoResultados]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    WITH MovimientosResultados AS (
        SELECT
            C.Clase, C.Codigo, C.Nombre AS Cuenta, C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND C.Clase IN ('Ingreso', 'Costo', 'Gasto')
          AND A.PeriodoID = @PeriodoID
        GROUP BY C.Clase, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase, Codigo, Cuenta,
        CASE
            WHEN Naturaleza = 'Acreedora' THEN (TotalHaber - TotalDebe)
            ELSE (TotalDebe - TotalHaber)
        END AS SaldoNeto
    FROM MovimientosResultados
    WHERE (TotalDebe - TotalHaber) <> 0
    ORDER BY
        CASE WHEN Clase = 'Ingreso' THEN 1
             WHEN Clase = 'Costo' THEN 2
             ELSE 3 END, Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanzaComprobacion]
    @Mes INT,
    @Anio INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Inicio DATE = DATEFROMPARTS(@Anio, @Mes, 1);
    DECLARE @Fin DATE = DATEADD(MONTH, 1, @Inicio);

    SELECT
        C.Codigo, C.Nombre, C.Clase, C.Naturaleza,
        ISNULL(SUM(CASE WHEN A.Fecha < @Inicio THEN (CASE WHEN C.Naturaleza = 'Deudora' THEN D.Debe - D.Haber ELSE D.Haber - D.Debe END) ELSE 0 END), 0) AS SaldoAnterior,
        ISNULL(SUM(CASE WHEN A.Fecha >= @Inicio AND A.Fecha < @Fin THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
        ISNULL(SUM(CASE WHEN A.Fecha >= @Inicio AND A.Fecha < @Fin THEN D.Haber ELSE 0 END), 0) AS TotalHaber
    FROM [contabilidad].[CatalogoCuentas] C
    LEFT JOIN [contabilidad].[DetalleAsientos] D ON C.ID = D.CuentaID
    LEFT JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID AND A.Estado IN ('Contabilizado', 'Anulado') AND A.Fecha < @Fin
    WHERE C.EsTransaccional = 1
    GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza
    HAVING ISNULL(SUM(CASE WHEN A.Fecha < @Fin THEN D.Debe ELSE 0 END), 0) > 0
        OR ISNULL(SUM(CASE WHEN A.Fecha < @Fin THEN D.Haber ELSE 0 END), 0) > 0
    ORDER BY C.Codigo;
END
GO

-- ============================================================================
-- 8. ESQUEMA [fiscal]: BITÁCORA FISCAL Y PREPARACIÓN TRIBUTARIA DGI
-- ============================================================================

CREATE OR ALTER PROCEDURE [fiscal].[sp_RegistrarBitacoraFiscal]
    @UsuarioID INT = NULL,
    @Accion NVARCHAR(50),
    @Entidad NVARCHAR(50),
    @EntidadID INT = NULL,
    @Detalle NVARCHAR(MAX),
    @IP VARCHAR(45) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [fiscal].[BitacoraFiscal] (Fecha, UsuarioID, Accion, Entidad, EntidadID, Detalle, IP)
    VALUES (SYSUTCDATETIME(), @UsuarioID, @Accion, @Entidad, @EntidadID, @Detalle, @IP);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarEventosBitacoraFiscal]
    @Top INT = 50,
    @PrefijoAccion NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@Top)
        ID, Fecha, UsuarioID, Accion, Entidad, EntidadID, Detalle, IP
    FROM [fiscal].[BitacoraFiscal]
    WHERE (@PrefijoAccion IS NULL OR Accion LIKE @PrefijoAccion + '%')
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarPeriodosDGI]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 120 ID, Desde, Hasta, Estado
    FROM [fiscal].[DGI_Periodos]
    ORDER BY Desde DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarRevisionesDGI]
    @PeriodoID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor,
        r.ResultadoJSON, r.CreadoEn, r.CreadoPor, r.AprobadoPor, p.Desde, p.Hasta
    FROM [fiscal].[DGI_Revisiones] r
    JOIN [fiscal].[DGI_Periodos] p ON p.ID = r.PeriodoID
    WHERE (@PeriodoID IS NULL OR r.PeriodoID = @PeriodoID)
    ORDER BY r.ID DESC;
END
GO

-- ============================================================================
-- 8.B CATÁLOGO EXTENDIDO DE PROCEDIMIENTOS OPERATIVOS, CONTABLES, RRHH Y FISCALES
-- ============================================================================

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceComprobacionCorte]
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel,
        ISNULL(SUM(D.Debe), 0) AS TotalDebe,
        ISNULL(SUM(D.Haber), 0) AS TotalHaber,
        CASE
            WHEN C.Naturaleza = 'Deudora' THEN ISNULL(SUM(D.Debe), 0) - ISNULL(SUM(D.Haber), 0)
            ELSE ISNULL(SUM(D.Haber), 0) - ISNULL(SUM(D.Debe), 0)
        END AS SaldoFinal
    FROM [contabilidad].[CatalogoCuentas] C
    INNER JOIN [contabilidad].[DetalleAsientos] D ON D.CuentaID = C.ID
    INNER JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    WHERE A.Estado IN ('Contabilizado', 'Anulado')
      AND C.EsTransaccional = 1
      AND A.Fecha < DATEADD(DAY, 1, CAST(@FechaCorte AS DATE))
    GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel
    HAVING ISNULL(SUM(D.Debe), 0) <> 0 OR ISNULL(SUM(D.Haber), 0) <> 0
    ORDER BY C.Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceComprobacionGeneral]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel,
        ISNULL(SUM(D.Debe), 0) AS TotalDebe,
        ISNULL(SUM(D.Haber), 0) AS TotalHaber,
        CASE
            WHEN C.Naturaleza = 'Deudora' THEN ISNULL(SUM(D.Debe), 0) - ISNULL(SUM(D.Haber), 0)
            ELSE ISNULL(SUM(D.Haber), 0) - ISNULL(SUM(D.Debe), 0)
        END AS SaldoFinal
    FROM [contabilidad].[CatalogoCuentas] C
    INNER JOIN [contabilidad].[DetalleAsientos] D ON D.CuentaID = C.ID
    INNER JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    WHERE A.Estado IN ('Contabilizado', 'Anulado')
      AND C.EsTransaccional = 1
    GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel
    HAVING ISNULL(SUM(D.Debe), 0) <> 0 OR ISNULL(SUM(D.Haber), 0) <> 0
    ORDER BY C.Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceComprobacionPeriodo]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel,
        ISNULL(SUM(D.Debe), 0) AS TotalDebe,
        ISNULL(SUM(D.Haber), 0) AS TotalHaber,
        CASE
            WHEN C.Naturaleza = 'Deudora' THEN ISNULL(SUM(D.Debe), 0) - ISNULL(SUM(D.Haber), 0)
            ELSE ISNULL(SUM(D.Haber), 0) - ISNULL(SUM(D.Debe), 0)
        END AS SaldoFinal
    FROM [contabilidad].[CatalogoCuentas] C
    INNER JOIN [contabilidad].[DetalleAsientos] D ON D.CuentaID = C.ID
    INNER JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    WHERE A.Estado IN ('Contabilizado', 'Anulado')
      AND C.EsTransaccional = 1
      AND A.PeriodoID = @PeriodoID
    GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel
    HAVING ISNULL(SUM(D.Debe), 0) <> 0 OR ISNULL(SUM(D.Haber), 0) <> 0
    ORDER BY C.Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceGeneralCorte]
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;
    WITH SaldosHistoricos AS (
        SELECT
            C.Clase, C.Grupo, C.Codigo, C.Nombre AS Cuenta, C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND A.Fecha < DATEADD(DAY, 1, CAST(@FechaCorte AS DATE))
        GROUP BY C.Clase, C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase, Grupo, Codigo, Cuenta,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (TotalDebe - TotalHaber)
            ELSE (TotalHaber - TotalDebe)
        END AS SaldoFinal
    FROM SaldosHistoricos
    WHERE (TotalDebe - TotalHaber) <> 0
    ORDER BY Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerCatalogoCuentasActivas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Codigo, Nombre, Clase, Grupo, Naturaleza,
           Nivel, EsTransaccional, Descripcion, CuentaPadreID, Activa
    FROM [contabilidad].[CatalogoCuentas]
    WHERE Activa = 1
    ORDER BY OrdenVisualizacion, Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerCatalogoCuentasTransaccionales]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Codigo, Nombre, Clase, Grupo, Naturaleza,
           Nivel, EsTransaccional, Descripcion, CuentaPadreID, Activa
    FROM [contabilidad].[CatalogoCuentas]
    WHERE Activa = 1 AND EsTransaccional = 1
    ORDER BY OrdenVisualizacion, Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerEstadoResultadosPeriodo]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    WITH MovimientosResultados AS (
        SELECT
            C.Clase, C.Codigo, C.Nombre AS Cuenta, C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE A.Estado IN ('Contabilizado', 'Anulado')
          AND C.Clase IN ('Ingreso', 'Costo', 'Gasto')
          AND A.PeriodoID = @PeriodoID
        GROUP BY C.Clase, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase, Codigo, Cuenta,
        CASE
            WHEN Naturaleza = 'Acreedora' THEN (TotalHaber - TotalDebe)
            ELSE (TotalDebe - TotalHaber)
        END AS SaldoNeto
    FROM MovimientosResultados
    WHERE (TotalDebe - TotalHaber) <> 0
    ORDER BY
        CASE WHEN Clase = 'Ingreso' THEN 1
             WHEN Clase = 'Costo' THEN 2
             ELSE 3 END, Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerFuenteAsientoDGI]
    @ID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NumeroComprobante, Fecha, Descripcion, Estado, ReferenciaExterna
    FROM [contabilidad].[AsientosDiario]
    WHERE ID = @ID;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerMovimientosLibroMayor]
    @CuentaCodigo VARCHAR(50),
    @PeriodoID INT = NULL,
    @FechaInicio DATETIME2 = NULL,
    @FechaFin DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        A.Fecha,
        A.NumeroComprobante,
        A.Descripcion AS DescripcionAsiento,
        D.Descripcion AS DescripcionLinea,
        D.Debe,
        D.Haber,
        A.ReferenciaExterna
    FROM [contabilidad].[DetalleAsientos] D
    INNER JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    INNER JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
    WHERE C.Codigo = @CuentaCodigo
      AND A.Estado IN ('Contabilizado', 'Anulado')
      AND (@PeriodoID IS NULL OR A.PeriodoID = @PeriodoID)
      AND (@FechaInicio IS NULL OR A.Fecha >= @FechaInicio)
      AND (@FechaFin IS NULL OR A.Fecha < DATEADD(DAY, 1, CAST(@FechaFin AS DATE)))
    ORDER BY A.Fecha, A.ID;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoCuentaCorte]
    @FechaCorte DATE,
    @CuentaCodigo VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Naturaleza,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber
    FROM [contabilidad].[CatalogoCuentas] C
    LEFT JOIN [contabilidad].[DetalleAsientos] D ON D.CuentaID = C.ID
    LEFT JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        AND A.Estado IN ('Contabilizado', 'Anulado')
        AND A.Fecha < DATEADD(DAY, 1, CAST(@FechaCorte AS DATE))
    WHERE C.Codigo = @CuentaCodigo
    GROUP BY C.Naturaleza;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoCuentaTotal]
    @CuentaCodigo VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Naturaleza,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber
    FROM [contabilidad].[CatalogoCuentas] C
    LEFT JOIN [contabilidad].[DetalleAsientos] D ON D.CuentaID = C.ID
    LEFT JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        AND A.Estado IN ('Contabilizado', 'Anulado')
    WHERE C.Codigo = @CuentaCodigo
    GROUP BY C.Naturaleza;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_AceptarCotizacionCliente]
    @CotizacionID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
        DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
        DECLARE @CtxRol NVARCHAR(50) = TRY_CAST(SESSION_CONTEXT(N'rol') AS NVARCHAR(50));

        IF IS_MEMBER('db_rol_portal_cliente') = 1 OR @CtxRol IN (N'Cliente', N'Invitado')
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM [crm].[Cotizaciones]
                WHERE ID = @CotizacionID
                  AND (
                      (@CtxRol = N'Cliente' AND @CtxUsuarioID IS NOT NULL AND ClienteID = @CtxUsuarioID)
                      OR (ClienteID IS NULL AND @CtxSessionID IS NOT NULL AND SessionID = @CtxSessionID)
                  )
            )
                THROW 52026, 'No autorizado: la cotización no pertenece al cliente o sesión actual.', 1;
        END

        SET NOCOUNT OFF;
        UPDATE [crm].[Cotizaciones]
        SET Estado = 'Aceptada'
        WHERE ID = @CotizacionID
          AND Estado = 'Cotizada';
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_AceptarCotizacionCliente';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_CancelarCotizacionCliente]
    @CotizacionID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
        DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
        DECLARE @CtxRol NVARCHAR(50) = TRY_CAST(SESSION_CONTEXT(N'rol') AS NVARCHAR(50));

        IF IS_MEMBER('db_rol_portal_cliente') = 1 OR @CtxRol IN (N'Cliente', N'Invitado')
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM [crm].[Cotizaciones]
                WHERE ID = @CotizacionID
                  AND (
                      (@CtxRol = N'Cliente' AND @CtxUsuarioID IS NOT NULL AND ClienteID = @CtxUsuarioID)
                      OR (ClienteID IS NULL AND @CtxSessionID IS NOT NULL AND SessionID = @CtxSessionID)
                  )
            )
                THROW 52026, 'No autorizado: la cotización no pertenece al cliente o sesión actual.', 1;
        END

        SET NOCOUNT OFF;
        UPDATE [crm].[Cotizaciones]
        SET Estado = 'Rechazada'
        WHERE ID = @CotizacionID
          AND Estado IN ('Pendiente', 'Cotizada');
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_CancelarCotizacionCliente';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_CotizarPedidoAdmin]
    @PrecioCotizado DECIMAL(18,2),
    @CotizacionID INT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        IF IS_MEMBER('db_rol_portal_cliente') = 1
           OR TRY_CAST(SESSION_CONTEXT(N'rol') AS NVARCHAR(50)) IN (N'Cliente', N'Invitado')
            THROW 52025, 'Operación administrativa de precios no autorizada para el portal de clientes.', 1;

        IF @PrecioCotizado IS NULL OR @PrecioCotizado <= 0
            THROW 52027, 'El precio cotizado debe ser mayor a cero.', 1;

        SET NOCOUNT OFF;
        UPDATE [crm].[Cotizaciones]
        SET PrecioCotizado = @PrecioCotizado,
            Estado = 'Cotizada'
        WHERE ID = @CotizacionID
          AND Estado IN ('Pendiente', 'Cotizada');
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_CotizarPedidoAdmin';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionesPorClienteID]
    @ClienteID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    IF IS_MEMBER('db_rol_portal_cliente') = 1 AND @CtxUsuarioID IS NOT NULL AND @ClienteID <> @CtxUsuarioID
        THROW 52026, 'No autorizado: ClienteID no coincide con la sesión autenticada.', 1;

    SELECT ID, Especificaciones, FechaEntrega, RutaImagenReferencia, Estado, PrecioCotizado, TelefonoContacto
    FROM [crm].[Cotizaciones]
    WHERE ClienteID = @ClienteID
    ORDER BY FechaSolicitud DESC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionesPorSessionID]
    @SessionID VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
    IF IS_MEMBER('db_rol_portal_cliente') = 1 AND @CtxSessionID IS NOT NULL AND @SessionID <> @CtxSessionID
        THROW 52026, 'No autorizado: SessionID no coincide con la sesión activa.', 1;

    SELECT ID, Especificaciones, FechaEntrega, RutaImagenReferencia, Estado, PrecioCotizado, TelefonoContacto
    FROM [crm].[Cotizaciones]
    WHERE ClienteID IS NULL AND SessionID = @SessionID
    ORDER BY FechaSolicitud DESC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_VincularCotizacionPorID]
    @ClienteID INT,
    @CotizacionID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
    IF IS_MEMBER('db_rol_portal_cliente') = 1
    BEGIN
        IF @CtxUsuarioID IS NOT NULL AND @ClienteID <> @CtxUsuarioID
            THROW 52026, 'No autorizado: ClienteID no coincide con la sesión autenticada.', 1;
        IF NOT EXISTS (
            SELECT 1 FROM [crm].[Cotizaciones]
            WHERE ID = @CotizacionID
              AND ClienteID IS NULL
              AND @CtxSessionID IS NOT NULL
              AND SessionID = @CtxSessionID
        )
            THROW 52026, 'No autorizado: la cotización no pertenece a la sesión actual.', 1;
    END

    UPDATE [crm].[Cotizaciones]
    SET ClienteID = @ClienteID
    WHERE ID = @CotizacionID;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_VincularCotizacionesSesionCliente]
    @ClienteID INT,
    @SessionID VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CtxUsuarioID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    DECLARE @CtxSessionID VARCHAR(100) = TRY_CAST(SESSION_CONTEXT(N'cotizacion_session_id') AS VARCHAR(100));
    IF IS_MEMBER('db_rol_portal_cliente') = 1
    BEGIN
        IF @CtxUsuarioID IS NOT NULL AND @ClienteID <> @CtxUsuarioID
            THROW 52026, 'No autorizado: ClienteID no coincide con la sesión autenticada.', 1;
        IF @CtxSessionID IS NOT NULL AND @SessionID <> @CtxSessionID
            THROW 52026, 'No autorizado: SessionID no coincide con la sesión activa.', 1;
    END

    UPDATE [crm].[Cotizaciones]
    SET ClienteID = @ClienteID
    WHERE ClienteID IS NULL AND SessionID = @SessionID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_HistorialRevisionesDGIPorPeriodo]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.ResultadoJSON,
        r.CreadoEn, r.CreadoPor, r.AprobadoPor, p.Desde, p.Hasta
    FROM [fiscal].[DGI_Revisiones] r
    JOIN [fiscal].[DGI_Periodos] p ON p.ID = r.PeriodoID
    WHERE r.PeriodoID = @PeriodoID
    ORDER BY r.ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_HistorialRevisionesDGITodas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.ResultadoJSON,
        r.CreadoEn, r.CreadoPor, r.AprobadoPor, p.Desde, p.Hasta
    FROM [fiscal].[DGI_Revisiones] r
    JOIN [fiscal].[DGI_Periodos] p ON p.ID = r.PeriodoID
    ORDER BY r.ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_MonitorDetallesEncargosActivos]
    @FacturaIDsJSON NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        df.ID, df.FacturaID, ISNULL(p.Nombre, 'Producto') AS Nombre,
        df.Cantidad, df.PrecioUnitario,
        i.ID AS IngredienteID, i.Nombre AS IngredienteNombre
    FROM [ventas].[DetalleFacturas] df
    LEFT JOIN [catalogo].[Productos] p ON p.ID = df.ProductoID
    LEFT JOIN [ventas].[DetalleIngredientes] di ON di.DetalleFacturaID = df.ID
    LEFT JOIN [catalogo].[Ingredientes] i ON i.ID = di.IngredienteID
    WHERE df.FacturaID IN (SELECT TRY_CAST([value] AS INT) FROM OPENJSON(@FacturaIDsJSON))
    ORDER BY df.ID, i.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_MonitorEncargosActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.ID, f.NumeroFactura, f.CodigoSeguimiento, f.FechaHora, f.Total,
        e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones,
        e.RutaImagenReferencia, e.TelefonoContacto,
        c.Nombre AS ClienteNombre, c.Telefono AS ClienteTelefono
    FROM [ventas].[Facturas] f
    JOIN [ventas].[Encargos] e ON e.FacturaID = f.ID
    LEFT JOIN [crm].[Clientes] c ON f.ClienteID = c.ID
    WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada')
      AND e.Estado <> 'Entregado'
    ORDER BY e.FechaEntrega ASC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerFuenteCompraDGI]
    @ID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.ID, c.Fecha, c.FacturaProveedor, p.Nombre AS Proveedor, c.MateriaPrimaID, c.Cantidad, c.CostoTotal, c.IVADocumentado
    FROM [produccion].[ComprasMateriaPrima] c
    LEFT JOIN [produccion].[Proveedores] p ON p.ID = c.ProveedorID
    WHERE c.ID = @ID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_VerificarNominaExistenteAguinaldo]
    @EmpleadoID INT,
    @PeriodoFin DATE,
    @PeriodoInicio DATE
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Estado
    FROM [rrhh].[Nomina]
    WHERE EmpleadoID = @EmpleadoID
      AND PeriodoInicio <= @PeriodoFin
      AND PeriodoFin >= @PeriodoInicio
      AND SalarioBruto = 0
      AND Estado IN ('Contabilizada', 'Pagada');
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_VerificarNominaExistenteMensual]
    @EmpleadoID INT,
    @PeriodoFin DATE,
    @PeriodoInicio DATE
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Estado
    FROM [rrhh].[Nomina]
    WHERE EmpleadoID = @EmpleadoID
      AND PeriodoInicio <= @PeriodoFin
      AND PeriodoFin >= @PeriodoInicio
      AND SalarioBruto > 0
      AND Estado IN ('Contabilizada', 'Pagada');
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_LimpiarBorradoresNominaPeriodo]
    @EmpleadoID INT,
    @PeriodoFin DATE,
    @PeriodoInicio DATE,
    @EsAguinaldo BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    IF @EsAguinaldo = 1
    BEGIN
        DELETE FROM [rrhh].[Nomina]
        WHERE EmpleadoID = @EmpleadoID
          AND PeriodoInicio <= @PeriodoFin
          AND PeriodoFin >= @PeriodoInicio
          AND SalarioBruto = 0
          AND Estado = 'Borrador';
    END
    ELSE
    BEGIN
        DELETE FROM [rrhh].[Nomina]
        WHERE EmpleadoID = @EmpleadoID
          AND PeriodoInicio <= @PeriodoFin
          AND PeriodoFin >= @PeriodoInicio
          AND SalarioBruto > 0
          AND Estado = 'Borrador';
    END
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_InsertarDesafioAuth]
    @Token VARCHAR(128),
    @Kind VARCHAR(32),
    @Subject NVARCHAR(128),
    @Verifier VARCHAR(255),
    @Secret VARCHAR(255),
    @Binding VARCHAR(128),
    @ExpiresAt BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [seguridad].[AuthChallenges] (
        Token, Kind, Subject, Verifier, Secret, Binding, ExpiresAt, Attempts, Verified, Consumed
    )
    VALUES (
        @Token, @Kind, @Subject, @Verifier, @Secret, @Binding, @ExpiresAt, 0, 0, 0
    );
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_LeerDesafioAuth]
    @Token VARCHAR(128),
    @ConBloqueo BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    IF @ConBloqueo = 1
    BEGIN
        SELECT Token, Kind, Subject, Verifier, Secret, Binding, ExpiresAt, Attempts, Verified, Consumed
        FROM [seguridad].[AuthChallenges] WITH (UPDLOCK, HOLDLOCK)
        WHERE Token = @Token;
    END
    ELSE
    BEGIN
        SELECT Token, Kind, Subject, Verifier, Secret, Binding, ExpiresAt, Attempts, Verified, Consumed
        FROM [seguridad].[AuthChallenges]
        WHERE Token = @Token;
    END
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerConfiguracionClave]
    @Clave NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Valor FROM [seguridad].[ConfiguracionSistema] WHERE Clave = @Clave;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerValorConfiguracion]
    @Clave NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Valor FROM [seguridad].[ConfiguracionSistema] WHERE Clave = @Clave;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarArqueoAuditLog]
    @ArqueoID INT,
    @UsuarioID INT,
    @Accion VARCHAR(50),
    @Detalle NVARCHAR(MAX),
    @DireccionIP VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [ventas].[ArqueoAuditLog] (ArqueoID, UsuarioID, Accion, Detalle, DireccionIP)
    VALUES (@ArqueoID, @UsuarioID, @Accion, @Detalle, @DireccionIP);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerFuenteFacturaDGI]
    @ID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NumeroFactura, FechaHora, Subtotal, IVA, Total, EstadoFiscal, FechaAnulacion, MotivoAnulacion, DocumentoJSON
    FROM [ventas].[Facturas]
    WHERE ID = @ID;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_RegistrarFacturaCompleta]
    @NumeroFactura VARCHAR(50),
    @CodigoSeguimiento VARCHAR(20),
    @UsuarioID INT,
    @ClienteID INT,
    @TurnoID INT,
    @Subtotal DECIMAL(18,2),
    @IVA DECIMAL(18,2),
    @Total DECIMAL(18,2),
    @EsEncargo BIT,
    @IncluyeRUC BIT,
    @ClaveSolicitud VARCHAR(100) = NULL,
    @FechaHora DATETIME2,
    @RazonSocial NVARCHAR(200) = NULL,
    @NumeroRUC VARCHAR(50) = NULL,
    @CarritoJSON NVARCHAR(MAX),
    @PagosJSON NVARCHAR(MAX),
    @FechaEntrega DATETIME2 = NULL,
    @NotasCliente NVARCHAR(MAX) = NULL,
    @Especificaciones NVARCHAR(MAX) = NULL,
    @RutaImagenReferencia VARCHAR(255) = NULL,
    @TelefonoContacto VARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @FacturaID INT;

        IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@TurnoID AND UsuarioID=@UsuarioID AND Cerrado=0)
            THROW 51024, 'La venta requiere la caja abierta del emisor.', 1;
        IF EXISTS (SELECT 1 FROM [ventas].[ArqueoCaja] WHERE TurnoID=@TurnoID AND EstadoArqueo IN ('Pendiente','Verificado'))
            THROW 51027, 'La caja receptora tiene un arqueo pendiente.', 1;

        INSERT INTO [ventas].[Facturas] (
            NumeroFactura, CodigoSeguimiento, UsuarioID, ClienteID, TurnoID,
            Subtotal, IVA, Total, EsEncargo, IncluyeRUC, ClaveSolicitud, FechaHora
        )
        VALUES (
            @NumeroFactura, @CodigoSeguimiento, @UsuarioID, @ClienteID, @TurnoID,
            @Subtotal, @IVA, @Total, @EsEncargo, @IncluyeRUC, @ClaveSolicitud, @FechaHora
        );
        SET @FacturaID = SCOPE_IDENTITY();

        IF @IncluyeRUC = 1 AND @NumeroRUC IS NOT NULL
        BEGIN
            INSERT INTO [ventas].[FacturasRUC] (FacturaID, RazonSocial, NumeroRUC)
            VALUES (@FacturaID, @RazonSocial, @NumeroRUC);
        END

        -- Procesar líneas del carrito e ingredientes adicionales desde JSON
        DECLARE @ItemKey NVARCHAR(50), @ItemJSON NVARCHAR(MAX);
        DECLARE cur_items CURSOR LOCAL FAST_FORWARD FOR
            SELECT [key], [value] FROM OPENJSON(@CarritoJSON);
        OPEN cur_items;
        FETCH NEXT FROM cur_items INTO @ItemKey, @ItemJSON;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            DECLARE @ProdID INT = TRY_CAST(JSON_VALUE(@ItemJSON, '$.id') AS INT);
            DECLARE @Cant INT = TRY_CAST(JSON_VALUE(@ItemJSON, '$.cantidad') AS INT);
            DECLARE @PrecioUnit DECIMAL(18,2) = TRY_CAST(JSON_VALUE(@ItemJSON, '$.precio') AS DECIMAL(18,2));
            DECLARE @SubItem DECIMAL(18,2) = TRY_CAST(JSON_VALUE(@ItemJSON, '$.subtotal') AS DECIMAL(18,2));
            DECLARE @CotID INT = TRY_CAST(JSON_VALUE(@ItemJSON, '$.cotizacion_id') AS INT);
            DECLARE @DetalleID INT;

            INSERT INTO [ventas].[DetalleFacturas] (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal)
            VALUES (@FacturaID, @ProdID, @Cant, @PrecioUnit, @SubItem);
            SET @DetalleID = SCOPE_IDENTITY();

            INSERT INTO [ventas].[DetalleIngredientes] (DetalleFacturaID, IngredienteID, PrecioAplicado)
            SELECT
                @DetalleID,
                TRY_CAST(JSON_VALUE([value], '$.id') AS INT),
                TRY_CAST(JSON_VALUE([value], '$.precio') AS DECIMAL(18,2))
            FROM OPENJSON(@ItemJSON, '$.detalle_ingredientes.ingredientes')
            WHERE TRY_CAST(JSON_VALUE([value], '$.id') AS INT) IS NOT NULL;

            IF @CotID IS NOT NULL
            BEGIN
                UPDATE [crm].[Cotizaciones]
                SET Estado = 'Aceptada'
                WHERE ID = @CotID AND Estado IN ('Cotizada', 'Aceptada');
            END

            FETCH NEXT FROM cur_items INTO @ItemKey, @ItemJSON;
        END
        CLOSE cur_items;
        DEALLOCATE cur_items;

        -- Procesar pagos desde JSON
        INSERT INTO [ventas].[Pagos] (
            FacturaID, MetodoPago, Monto, NombreTransferente, MonedaRegistro, TipoCambioAplicado, TurnoReceptorID, UsuarioReceptorID
        )
        SELECT
            @FacturaID,
            JSON_VALUE([value], '$.metodo'),
            TRY_CAST(JSON_VALUE([value], '$.monto') AS DECIMAL(18,2)),
            JSON_VALUE([value], '$.referencia'),
            'NIO',
            TRY_CAST(JSON_VALUE([value], '$.tipo_cambio') AS DECIMAL(18,4)), @TurnoID, @UsuarioID
        FROM OPENJSON(@PagosJSON);

        IF @EsEncargo = 1
        BEGIN
            INSERT INTO [ventas].[Encargos] (
                FacturaID, FechaEntrega, Estado, NotasCliente,
                Especificaciones, RutaImagenReferencia, TelefonoContacto
            )
            VALUES (
                @FacturaID, @FechaEntrega, 'Pendiente', @NotasCliente,
                @Especificaciones, @RutaImagenReferencia, @TelefonoContacto
            );
        END

        IF @ClienteID > 1
        BEGIN
            UPDATE [crm].[Clientes]
            SET TotalCompras = ISNULL(TotalCompras, 0) + 1
            WHERE ID = @ClienteID;

            UPDATE [crm].[Clientes]
            SET NivelConfianzaID = CASE
                WHEN TotalCompras >= 10 THEN 3
                WHEN TotalCompras >= 3 THEN 2
                ELSE 1
            END
            WHERE ID = @ClienteID;
        END

        SELECT CAST(@FacturaID AS INT) AS ID;
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'ventas.sp_RegistrarFacturaCompleta';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_SeguimientoEncargoPublico]
    @CodigoSeguimiento VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.NumeroFactura, f.FechaHora, f.Total, f.Subtotal, f.IVA,
        e.Estado, e.FechaEntrega, e.NotasCliente, e.Especificaciones, e.RutaImagenReferencia,
        c.Nombre AS NombreCliente
    FROM [ventas].[Facturas] f
    JOIN [ventas].[Encargos] e ON e.FacturaID = f.ID
    LEFT JOIN [crm].[Clientes] c ON f.ClienteID = c.ID
    WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada')
      AND f.CodigoSeguimiento = @CodigoSeguimiento;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_SeguimientoProductosPublico]
    @CodigoSeguimiento VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ISNULL(p.Nombre, 'Producto') AS Nombre,
        df.Cantidad, df.PrecioUnitario, df.Subtotal
    FROM [ventas].[DetalleFacturas] df
    LEFT JOIN [catalogo].[Productos] p ON df.ProductoID = p.ID
    JOIN [ventas].[Facturas] f ON df.FacturaID = f.ID
    WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal <> 'Anulada')
      AND f.CodigoSeguimiento = @CodigoSeguimiento;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ActualizarProductoConImagen]
    @P1 NVARCHAR(255) = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 INT = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[catalogo].[Productos] SET Nombre = @P1, PrecioBase = @P2, CategoriaID = @P3, PorcentajeDescuento = @P4, ImagenUrl = @P5 WHERE ID = @P6;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ActualizarProductoSinImagen]
    @P1 NVARCHAR(255) = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 INT = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[catalogo].[Productos] SET Nombre = @P1, PrecioBase = @P2, CategoriaID = @P3, PorcentajeDescuento = @P4 WHERE ID = @P5;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_CrearProductoAdmin]
    @P1 NVARCHAR(255) = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 INT = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[catalogo].[Productos] (Nombre, PrecioBase, CategoriaID, EsFicticio, Activo, PorcentajeDescuento, ImagenUrl) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3, 0, 1, @P4, @P5);
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ListarProductosFiscal]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID,Nombre,TasaIVA,MotivoExencion FROM[catalogo].[Productos] WHERE Activo=1 ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerCategorias]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre FROM[catalogo].[Categorias] ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerCategoriasConProductosActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DISTINCT c.ID, c.Nombre 
        FROM[catalogo].[Categorias] c
        JOIN[catalogo].[Productos] p ON p.CategoriaID = c.ID
        WHERE p.Activo = 1
        ORDER BY c.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerEstadoProducto]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Nombre, Activo FROM[catalogo].[Productos] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerImagenProducto]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ImagenUrl FROM[catalogo].[Productos] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerIngredientePorNombreActivo]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID,Nombre,PrecioAdicional FROM[catalogo].[Ingredientes] WHERE Nombre=@P1 AND Activo=1;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerIngredientesPOS]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, PrecioAdicional FROM[catalogo].[Ingredientes] WHERE Activo = 1 ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerProductoAdminPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Nombre, PrecioBase, CategoriaID, PorcentajeDescuento, ImagenUrl, Activo FROM[catalogo].[Productos] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerProductoBaseParaCotizacion]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, TasaIVA, MotivoExencion FROM[catalogo].[Productos] WHERE Activo=1 ORDER BY EsFicticio DESC, ID ASC;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerProductoParaCalculoVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Nombre,PrecioBase,PorcentajeDescuento,TasaIVA,MotivoExencion,EsFicticio FROM[catalogo].[Productos] WHERE ID=@P1 AND Activo=1;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerProductosPOS]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.PrecioBase, p.EsFicticio, p.PorcentajeDescuento, p.ImagenUrl, p.TasaIVA FROM[catalogo].[Productos] p JOIN[catalogo].[Categorias] c ON p.CategoriaID = c.ID WHERE p.Activo = 1 ORDER BY c.Nombre, p.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [catalogo].[sp_ObtenerProductosParaProduccion]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.ID, p.Nombre 
        FROM[catalogo].[Productos] p
        JOIN[catalogo].[Categorias] c ON p.CategoriaID = c.ID
        WHERE p.Activo = 1 AND c.Nombre != 'Bebidas'
        ORDER BY p.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ActualizarEmisorJSONAsiento]
    @P1 NVARCHAR(MAX) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[contabilidad].[AsientosDiario] SET EmisorJSON=@P1 WHERE ID=@P2;
END
GO

-- Shared-owner chain encapsulates issuer config and fiscal audit with no fiscal grant.
CREATE OR ALTER PROCEDURE [contabilidad].[sp_InicializarEmisorYAuditarAsiento]
    @AsientoID INT, @UsuarioID INT, @Numero NVARCHAR(255),
    @Referencia NVARCHAR(255)=NULL, @IP VARCHAR(45)=NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF NOT EXISTS (SELECT 1 FROM [contabilidad].[AsientosDiario] WHERE ID=@AsientoID AND UsuarioID=@UsuarioID AND Estado='Contabilizado' AND EmisorJSON IS NULL)
        THROW 51022, 'El asiento no admite inicialización de emisor.', 1;
    DECLARE @Emisor NVARCHAR(MAX), @Detalle NVARCHAR(MAX);
    SELECT @Emisor=N'{'+ISNULL(STUFF((
      SELECT N','+N'"'+STRING_ESCAPE(Clave,'json')+N'":'+
        CASE WHEN Valor IS NULL THEN N'null' ELSE N'"'+STRING_ESCAPE(Valor,'json')+N'"' END
      FROM [seguridad].[ConfiguracionSistema] WHERE Clave LIKE N'fiscal[_]%'
      ORDER BY Clave FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,N''),N'')+N'}';
    UPDATE [contabilidad].[AsientosDiario] SET EmisorJSON=@Emisor WHERE ID=@AsientoID;
    SET @Detalle=(SELECT @Numero AS numero,@Referencia AS referencia FOR JSON PATH,WITHOUT_ARRAY_WRAPPER,INCLUDE_NULL_VALUES);
    EXEC [fiscal].[sp_RegistrarBitacoraFiscal] @UsuarioID,N'ASIENTO',N'AsientosDiario',@AsientoID,@Detalle,@IP;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_CerrarPeriodoContable]
    @P1 INT = NULL,
    @P2 DATETIME2 = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[contabilidad].[PeriodosContables] SET Estado='Cerrado',CerradoPor=@P1,CerradoEn=@P2 WHERE ID=@P3;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ContabilidadEgresosDia]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[contabilidad].[EgresosPrivados] WHERE CONVERT(date, Fecha) = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ContabilidadEgresosMes]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[contabilidad].[EgresosPrivados] WHERE MONTH(Fecha) = @P1 AND YEAR(Fecha) = @P2;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ContabilidadValesPendientes]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[rrhh].[ValesEmpleados] WHERE Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ContarAsientosBorradorPeriodo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) FROM[contabilidad].[AsientosDiario] WHERE PeriodoID=@P1 AND Estado='Borrador';
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_InsertarCabeceraAsiento]
    @P1 DATETIME2 = NULL,
    @P2 INT = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 INT = NULL,
    @P7 INT = NULL,
    @P8 NVARCHAR(255) = NULL,
    @P9 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[contabilidad].[AsientosDiario]
                (Fecha, PeriodoID, Descripcion, ReferenciaExterna, TipoDocumento,
                 Estado, UsuarioID, TipoComprobanteID, NumeroComprobante, IP)
            OUTPUT INSERTED.ID
            VALUES (@P1, @P2, @P3, @P4, @P5, 'Contabilizado', @P6, @P7, @P8, @P9);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_InsertarEgresoPrivado]
    @P1 NVARCHAR(255) = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 INT = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[contabilidad].[EgresosPrivados] (Concepto, Monto, UsuarioID, Fecha) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3, @P4);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_InsertarLineaDetalleAsiento]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 4) = NULL,
    @P4 DECIMAL(18, 4) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[contabilidad].[DetalleAsientos]
                    (AsientoID, CuentaID, Debe, Haber, Descripcion, DocumentoRelacionado)
                VALUES (@P1, @P2, @P3, @P4, @P5, @P6);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_InsertarPeriodoContableAbierto]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[contabilidad].[PeriodosContables] (Mes, Anio, Estado) OUTPUT INSERTED.ID VALUES (@P1, @P2, 'Abierto');
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_InsertarValeEmpleado]
    @P1 INT = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[ValesEmpleados] (EmpleadoID, Monto, Fecha) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarEgresosPrivados]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT e.ID, e.Concepto, e.Monto, e.Fecha, u.NombreCompleto AS RegistradoPor FROM[contabilidad].[EgresosPrivados] e JOIN[seguridad].[Usuarios] u ON e.UsuarioID = u.ID ORDER BY e.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarPeriodosContablesFiscal]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID,Mes,Anio,Estado FROM[contabilidad].[PeriodosContables] ORDER BY Anio DESC,Mes DESC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarUltimosAsientosFiscal]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50 ID,NumeroComprobante,Fecha,Descripcion,Estado FROM[contabilidad].[AsientosDiario] ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarValesEmpleados]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT v.ID, u.NombreCompleto AS Empleado, v.Monto, v.Fecha, v.Descontado FROM[rrhh].[ValesEmpleados] v JOIN[seguridad].[Usuarios] u ON v.EmpleadoID = u.ID ORDER BY v.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarAsientoAnulado]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[contabilidad].[AsientosDiario] SET
                Estado = 'Anulado',
                AnuladoPor = @P1,
                FechaAnulacion = GETDATE(),
                MotivoAnulacion = @P2
            WHERE ID = @P3 AND Estado = 'Contabilizado';
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarValesDescontadosUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[ValesEmpleados] SET Descontado = 1 WHERE EmpleadoID = @P1 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerAnioMesPeriodo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Anio,Mes FROM[contabilidad].[PeriodosContables] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerAsientoDiarioPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM[contabilidad].[AsientosDiario] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerAsientoParaReversion]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, PeriodoID, Descripcion, ReferenciaExterna, Estado
            FROM[contabilidad].[AsientosDiario] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerAsientosSaldoEncargoActivos]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[contabilidad].[AsientosDiario] WHERE ReferenciaExterna=@P1 AND Estado='Contabilizado';
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanzaMensualRango]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL,
    @P3 DATETIME2 = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT C.Codigo,C.Nombre,C.Naturaleza,
              SUM(CASE WHEN A.Fecha<@P1 THEN D.Debe-D.Haber ELSE 0 END) AS SaldoAnterior,
              SUM(CASE WHEN A.Fecha>=@P2 THEN D.Debe ELSE 0 END) AS TotalDebe,
              SUM(CASE WHEN A.Fecha>=@P3 THEN D.Haber ELSE 0 END) AS TotalHaber,
              SUM(D.Debe-D.Haber) AS SaldoFinal
            FROM[contabilidad].[CatalogoCuentas] C JOIN[contabilidad].[DetalleAsientos] D ON C.ID=D.CuentaID
            JOIN[contabilidad].[AsientosDiario] A ON A.ID=D.AsientoID
            WHERE A.Estado IN ('Contabilizado','Anulado') AND A.Fecha<@P4 AND C.EsTransaccional=1
            GROUP BY C.Codigo,C.Nombre,C.Naturaleza ORDER BY C.Codigo;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerCodigoCuentaPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Codigo FROM[contabilidad].[CatalogoCuentas] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerCuentaActivaPorCodigo]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[contabilidad].[CatalogoCuentas] WHERE Codigo = @P1 AND Activa = 1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerDetallesAsientoImpresion]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.Codigo,c.Nombre,d.Descripcion,d.Debe,d.Haber FROM[contabilidad].[DetalleAsientos] d JOIN[contabilidad].[CatalogoCuentas] c ON c.ID=d.CuentaID WHERE d.AsientoID=@P1 ORDER BY d.ID;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerDetallesAsientoParaReversion]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT C.Codigo, D.Debe, D.Haber, D.Descripcion
            FROM[contabilidad].[DetalleAsientos] D
            JOIN[contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
            WHERE D.AsientoID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerDetallesFuenteAsientoDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.Codigo,c.Nombre,d.Debe,d.Haber FROM[contabilidad].[DetalleAsientos] d
                JOIN[contabilidad].[CatalogoCuentas] c ON c.ID=d.CuentaID WHERE d.AsientoID=@P1 ORDER BY d.ID;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerEsTransaccionalCuenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT EsTransaccional FROM[contabilidad].[CatalogoCuentas] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerFechaAsientoPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Fecha FROM[contabilidad].[AsientosDiario] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerMesAnioPeriodoPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Mes,Anio FROM[contabilidad].[PeriodosContables] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerNaturalezaCuenta]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Naturaleza FROM[contabilidad].[CatalogoCuentas] WHERE Codigo = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerPeriodoContablePorMesAnio]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Estado FROM[contabilidad].[PeriodosContables] WITH (UPDLOCK, HOLDLOCK) WHERE Mes = @P1 AND Anio = @P2;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerPeriodoIDPorMesAnio]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[contabilidad].[PeriodosContables] WHERE Mes = @P1 AND Anio = @P2;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerPeriodoParaCierre]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Mes,Anio,Estado FROM[contabilidad].[PeriodosContables] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoAnteriorLibroMayor]
    @P1 NVARCHAR(255) = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(D.Debe-D.Haber),0) FROM[contabilidad].[DetalleAsientos] D
              JOIN[contabilidad].[AsientosDiario] A ON D.AsientoID=A.ID JOIN[contabilidad].[CatalogoCuentas] C ON D.CuentaID=C.ID
              WHERE C.Codigo=@P1 AND A.Fecha<@P2 AND A.Estado IN ('Contabilizado','Anulado');
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSumaValesPendientesUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[rrhh].[ValesEmpleados] WHERE EmpleadoID = @P1 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_SiguienteNumeroComprobante]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[contabilidad].[TiposComprobante] WITH (UPDLOCK, HOLDLOCK)
            SET CorrelativoActual = CorrelativoActual + 1
            OUTPUT INSERTED.ID, INSERTED.Prefijo, INSERTED.CorrelativoActual
            WHERE Codigo = @P1;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_VerificarAsientosDescuadradosPeriodo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT A.ID FROM[contabilidad].[AsientosDiario] A LEFT JOIN[contabilidad].[DetalleAsientos] D ON D.AsientoID=A.ID
            WHERE A.PeriodoID=@P1 AND A.Estado IN ('Contabilizado','Anulado') GROUP BY A.ID
            HAVING COUNT(D.ID)<2 OR SUM(D.Debe)<>SUM(D.Haber) OR SUM(D.Debe)<=0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_VerificarCuentaTransaccionalActiva]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 1 FROM[contabilidad].[CatalogoCuentas] WHERE Codigo = @P1 AND Activa = 1 AND EsTransaccional = 1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ActualizarClienteAdmin]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 DATE = NULL,
    @P6 INT = NULL,
    @P7 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[crm].[Clientes] SET Nombre=@P1, Apellidos=@P2, Telefono=@P3, Genero=@P4, FechaNacimiento=@P5, NivelConfianzaID=@P6 WHERE ID=@P7 AND ID > 1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ActualizarNivelConfianzaCliente]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[crm].[Clientes] SET NivelConfianzaID=CASE WHEN TotalCompras>=10 THEN 3 WHEN TotalCompras>=3 THEN 2 ELSE 1 END WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ContarClientesReales]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(ID) FROM[crm].[Clientes] WHERE ID > 1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ContarClientesVIP]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(ID) FROM[crm].[Clientes] WHERE NivelConfianzaID = 3;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_DecrementarComprasCliente]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[crm].[Clientes] SET TotalCompras=CASE WHEN TotalCompras>0 THEN TotalCompras-1 ELSE 0 END WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_EstadisticaClientesPorNivel]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT nc.Nombre AS Nivel, COUNT(c.ID) AS Cantidad
        FROM[crm].[Clientes] c
        JOIN[crm].[NivelesConfianza] nc ON c.NivelConfianzaID = nc.ID
        WHERE c.ID > 1
        GROUP BY nc.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_IncrementarComprasCliente]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[crm].[Clientes] SET TotalCompras=ISNULL(TotalCompras,0)+1 WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_InsertarClienteRapido]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[crm].[Clientes](Nombre,Telefono,NivelConfianzaID) OUTPUT INSERTED.ID VALUES(@P1,@P2,1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_MarcarCotizacionAceptadaEnVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[crm].[Cotizaciones] SET Estado='Aceptada' WHERE ID=@P1 AND Estado IN ('Cotizada','Aceptada');
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionParaAceptarBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ClienteID, SessionID, Estado, PrecioCotizado, TelefonoContacto FROM[crm].[Cotizaciones] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionParaCalculoVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Especificaciones, PrecioCotizado FROM[crm].[Cotizaciones] WHERE ID=@P1 AND Estado IN ('Cotizada', 'Aceptada') AND PrecioCotizado IS NOT NULL;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionPorIDBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ClienteID, SessionID, Estado, TelefonoContacto FROM[crm].[Cotizaciones] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionesPendientesAdmin]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.*, cl.Nombre AS ClienteNombre 
        FROM[crm].[Cotizaciones] c
        LEFT JOIN[crm].[Clientes] cl ON c.ClienteID = cl.ID
        WHERE c.Estado IN ('Pendiente', 'Cotizada', 'Aceptada')
        ORDER BY CASE WHEN c.Estado = 'Pendiente' THEN 0 ELSE 1 END, c.FechaSolicitud ASC;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerPromedioVentasPorNivel]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT nc.Nombre, ISNULL(AVG(f.Total), 0) AS Promedio FROM[ventas].[Facturas] f JOIN[crm].[Clientes] c ON f.ClienteID = c.ID JOIN[crm].[NivelesConfianza] nc ON c.NivelConfianzaID = nc.ID WHERE f.EstadoFiscal='Emitida' GROUP BY nc.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_RegistrarClienteVerificado]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 DATE = NULL,
    @P7 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[crm].[Clientes] (Nombre, Apellidos, Telefono, PasswordHash, Genero,
                                     FechaNacimiento, RutaFotoPerfil, EsInvitado, NivelConfianzaID)
               VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, 0, 1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_VerificarNivelConfianzaExiste]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[crm].[NivelesConfianza] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_VerificarTelefonoClienteDuplicado]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[crm].[Clientes] WHERE Telefono = @P1 AND ID <> @P2;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ActualizarEstadoPeriodoDGI]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[fiscal].[DGI_Periodos] SET Estado=@P1 WHERE ID=@P2;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_AprobarRevisionDGI]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[fiscal].[DGI_Revisiones] SET Estado='APROBADO',AprobadoPor=@P1,
        AprobadoEn=SYSUTCDATETIME() WHERE ID=@P2;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_CrearPeriodoDGI]
    @P1 DATE = NULL,
    @P2 DATE = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[fiscal].[DGI_Periodos](Desde,Hasta,CreadoPor) OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_InsertarExportacionDGI]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 VARBINARY(MAX) = NULL,
    @P5 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[fiscal].[DGI_Exportaciones](RevisionID,Nombre,SHA256,Archivo,UsuarioID)
                OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3,@P4,@P5);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_InsertarObservacionDGI]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(1000) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[fiscal].[DGI_Observaciones](RevisionID,Hallazgo,Comentario,UsuarioID) VALUES(@P1,@P2,@P3,@P4);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_InsertarRevisionDGI]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 NVARCHAR(MAX) = NULL,
    @P7 NVARCHAR(MAX) = NULL,
    @P8 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[fiscal].[DGI_Revisiones](PeriodoID,Obligacion,Version,Motor,Huella,
        SnapshotJSON,ResultadoJSON,CreadoPor) OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3,@P4,@P5,@P6,@P7,@P8);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarBitacoraRevisionDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Fecha,UsuarioID,Accion FROM[fiscal].[BitacoraFiscal] WHERE Entidad='DGI_Revision' AND EntidadID=@P1 ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarEventosBitacoraDGI]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 30 Fecha,UsuarioID,Accion,EntidadID FROM[fiscal].[BitacoraFiscal] WHERE Accion LIKE 'DGI[_]%' ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarExportacionesRevisionDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID,Nombre,SHA256,Fecha,UsuarioID FROM[fiscal].[DGI_Exportaciones] WHERE RevisionID=@P1 ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarObservacionesRevisionDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Hallazgo,Comentario,UsuarioID,Fecha FROM[fiscal].[DGI_Observaciones] WHERE RevisionID=@P1 ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_MarcarRevisionDGIExportada]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[fiscal].[DGI_Revisiones] SET Estado='EXPORTADO' WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_MarcarRevisionDGIObsoleta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[fiscal].[DGI_Revisiones] SET Estado='OBSOLETO' WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerExportacionDGIPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT RevisionID,Nombre,Archivo,SHA256 FROM[fiscal].[DGI_Exportaciones] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerPeriodoDGIPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID,Desde,Hasta,Estado FROM[fiscal].[DGI_Periodos] WITH (UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerPeriodoDGIPorRango]
    @P1 DATE = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[fiscal].[DGI_Periodos] WITH (UPDLOCK,HOLDLOCK) WHERE Desde=@P1 AND Hasta=@P2;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerPrimeraExportacionRevisionDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID FROM[fiscal].[DGI_Exportaciones] WHERE RevisionID=@P1 ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerRevisionDGIPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM[fiscal].[DGI_Revisiones] WITH (UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerUltimaRevisionDGI]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID,Version,Huella,Motor,Estado FROM[fiscal].[DGI_Revisiones] WITH (UPDLOCK,HOLDLOCK)
        WHERE PeriodoID=@P1 AND Obligacion=@P2 ORDER BY Version DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ObtenerUltimasRevisionesPeriodoDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[fiscal].[DGI_Revisiones] r WHERE PeriodoID=@P1 AND Version=
            (SELECT MAX(x.Version) FROM[fiscal].[DGI_Revisiones] x WHERE x.PeriodoID=r.PeriodoID AND x.Obligacion=r.Obligacion);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_RegistrarBitacoraFiscalUTC]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 INT = NULL,
    @P5 NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[fiscal].[BitacoraFiscal](Fecha,UsuarioID,Accion,Entidad,EntidadID,Detalle)
        VALUES(SYSUTCDATETIME(),@P1,@P2,@P3,@P4,@P5);
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_RegistrarNotaRevisionDGI]
    @P1 INT = NULL,
    @P2 NVARCHAR(1000) = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[fiscal].[DGI_Revisiones] SET Estado='EN_REVISION',RevisadoPor=@P1,
        RevisadoEn=SYSUTCDATETIME(),NotaRevision=@P2 WHERE ID=@P3;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIAsientos]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID AS id,NumeroComprobante AS numero,Fecha AS fecha,
        Estado AS estado,Descripcion AS descripcion,ReferenciaExterna AS referencia
        FROM[contabilidad].[AsientosDiario] WHERE Fecha>=@P1 AND Fecha<@P2 ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGICompras]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.ID AS id,c.Fecha AS fecha,c.FacturaProveedor AS numero,
        c.ProveedorID AS proveedor_id,p.Nombre AS proveedor,c.MateriaPrimaID AS materia_id,
        c.Cantidad AS cantidad,c.CostoTotal AS total,c.IVADocumentado AS iva
        FROM[produccion].[ComprasMateriaPrima] c LEFT JOIN[produccion].[Proveedores] p ON p.ID=c.ProveedorID
        WHERE c.Fecha>=@P1 AND c.Fecha<@P2 ORDER BY c.ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIDetallesAsientos]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT d.ID AS id,d.AsientoID AS asiento_id,c.Codigo AS cuenta,
        c.Nombre AS nombre,c.Clase AS clase,d.Debe AS debe,d.Haber AS haber
        FROM[contabilidad].[DetalleAsientos] d JOIN[contabilidad].[AsientosDiario] a ON a.ID=d.AsientoID
        JOIN[contabilidad].[CatalogoCuentas] c ON c.ID=d.CuentaID
        WHERE a.Fecha>=@P1 AND a.Fecha<@P2 ORDER BY d.ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIDetallesVentas]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL,
    @P3 DATETIME2 = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT d.ID AS id,d.FacturaID AS factura_id,d.ProductoID AS producto_id,
        d.Cantidad AS cantidad,d.PrecioUnitario AS precio,d.Subtotal AS subtotal
        FROM[ventas].[DetalleFacturas] d JOIN[ventas].[Facturas] f ON f.ID=d.FacturaID
        WHERE (f.FechaHora>=@P1 AND f.FechaHora<@P2) OR (f.FechaAnulacion>=@P3 AND f.FechaAnulacion<@P4)
        ORDER BY d.ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIVentasCandidatas]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL,
    @P3 DATETIME2 = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT f.ID AS id,f.NumeroFactura AS numero,f.FechaHora AS fecha,
        f.Subtotal AS base,f.IVA AS iva,f.Total AS total,f.EstadoFiscal AS estado,
        f.FechaAnulacion AS anulada_en,f.MotivoAnulacion AS motivo_anulacion,
        f.DocumentoJSON AS documento,a.Fecha AS fecha_asiento,r.Fecha AS fecha_reversion
        FROM[ventas].[Facturas] f OUTER APPLY (SELECT TRY_CONVERT(int,JSON_VALUE(
          CASE WHEN ISJSON(f.DocumentoJSON)=1 THEN f.DocumentoJSON ELSE N'{}' END,'$.asiento_id')) AS AsientoID) j
        LEFT JOIN[contabilidad].[AsientosDiario] a ON a.ID=j.AsientoID
        OUTER APPLY (SELECT TOP 1 Fecha FROM[contabilidad].[AsientosDiario] v
          WHERE v.ReferenciaExterna=CONCAT('REV-',j.AsientoID) AND v.TipoDocumento=N'Reversión' ORDER BY v.ID) r
        WHERE (f.FechaHora>=@P1 AND f.FechaHora<@P2) OR (f.FechaAnulacion>=@P3 AND f.FechaAnulacion<@P4)
        ORDER BY f.ID;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_VerificarEsquemaDGI]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COALESCE(OBJECT_ID('fiscal.DGI_Revisiones','U'), OBJECT_ID('dbo.DGI_Revisiones','U'));
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarEstadoEncargoCompare]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    -- The invoice lock is shared with fiscal annulment and retained by caller's transaction.
    DECLARE @FacturaID INT;
    SELECT @FacturaID=ID FROM [ventas].[Facturas] WITH(UPDLOCK,HOLDLOCK)
      WHERE CodigoSeguimiento=@P2 AND EstadoFiscal='Emitida';
    IF @P1='Entregado' AND IS_MEMBER('db_rol_produccion')=1 AND EXISTS (
        SELECT 1 FROM [ventas].[Facturas] f WHERE f.ID=@FacturaID AND
          f.Total>ISNULL((SELECT SUM(p.Monto) FROM [ventas].[Pagos] p WHERE p.FacturaID=f.ID),0))
        THROW 51032, 'El cobro pendiente debe confirmarlo un cajero con turno abierto.', 1;
    UPDATE e SET Estado = @P1 FROM[ventas].[Encargos] AS e JOIN[ventas].[Facturas] AS f ON e.FacturaID = f.ID
      WHERE f.ID=@FacturaID AND f.EstadoFiscal='Emitida' AND e.Estado=@P3;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarMateriaPrima]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[produccion].[MateriaPrima] SET Nombre=@P1, UnidadMedidaID=@P2, StockMinimo=@P3 WHERE ID=@P4;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarProveedorActivo]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[produccion].[Proveedores] SET Nombre=@P1, Telefono=@P2 WHERE ID=@P3 AND Activo=1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ContabilidadComprasDia]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(CostoTotal), 0) FROM[produccion].[ComprasMateriaPrima] WHERE CONVERT(date, Fecha) = @P1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ContabilidadComprasMes]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(CostoTotal), 0) FROM[produccion].[ComprasMateriaPrima] WHERE MONTH(Fecha) = @P1 AND YEAR(Fecha) = @P2;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_CrearMateriaPrima]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[produccion].[MateriaPrima] (Nombre, UnidadMedidaID, StockMinimo, StockActual) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3, 0.0);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_CrearProveedor]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[produccion].[Proveedores] (Nombre, Telefono) OUTPUT INSERTED.ID VALUES (@P1, @P2);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_CrearUnidadMedida]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[catalogo].[UnidadesMedida] (Nombre, Abreviatura) OUTPUT INSERTED.ID VALUES (@P1, @P2);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_DashboardEncargosResumen]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) AS Pendientes,        ISNULL(SUM(CASE WHEN e.Estado = 'Listo' THEN 1 ELSE 0 END), 0) AS Listos,        ISNULL(SUM(CASE WHEN CONVERT(date, e.FechaEntrega) < @P1 THEN 1 ELSE 0 END), 0) AS Atrasados FROM[ventas].[Encargos] e JOIN[ventas].[Facturas] f ON e.FacturaID = f.ID WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal != 'Anulada') AND e.Estado != 'Entregado';
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_DescontarStockMateriaPrimaLote]
    @P1 DECIMAL(38, 19) = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(38, 19) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[produccion].[MateriaPrima] SET StockActual = StockActual - @P1 WHERE ID = @P2 AND StockActual >= @P3;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_EstadisticaMermasMes]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.Nombre, m.Motivo, SUM(m.Cantidad) AS Total
        FROM[produccion].[Mermas] m
        JOIN[catalogo].[Productos] p ON m.ProductoID = p.ID
        WHERE m.Fecha >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre, m.Motivo
        ORDER BY Total DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_EstadisticaPronosticoAbastecimiento]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 
            m.Nombre, 
            u.Abreviatura, 
            m.StockActual,
            ISNULL(SUM(cl.CantidadUsada) / 30.0, 0) AS ConsumoPromedioDiario
        FROM[produccion].[MateriaPrima] m
        JOIN[catalogo].[UnidadesMedida] u ON m.UnidadMedidaID = u.ID
        JOIN[produccion].[ConsumoLote] cl ON m.ID = cl.MateriaPrimaID
        JOIN[produccion].[ProduccionLotes] pl ON cl.LoteID = pl.ID
        WHERE pl.Fecha >= DATEADD(DAY, -30, GETDATE())
        GROUP BY m.ID, m.Nombre, u.Abreviatura, m.StockActual
        HAVING ISNULL(SUM(cl.CantidadUsada), 0) > 0;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_EstadisticaRendimientoLotes]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 20 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.CantidadEsperada, pl.Fecha
        FROM[produccion].[ProduccionLotes] pl
        JOIN[catalogo].[Productos] p ON pl.ProductoID = p.ID
        WHERE pl.CantidadEsperada IS NOT NULL
        ORDER BY pl.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarCompraMateriaPrima]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[produccion].[ComprasMateriaPrima] (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarConsumoLote]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[produccion].[ConsumoLote] (LoteID, MateriaPrimaID, CantidadUsada) VALUES (@P1, @P2, @P3);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarEncargo]
    @P1 INT = NULL,
    @P2 DATETIME2 = NULL,
    @P3 NVARCHAR(500) = NULL,
    @P4 NVARCHAR(MAX) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[Encargos](FacturaID,FechaEntrega,Estado,NotasCliente,Especificaciones,RutaImagenReferencia,TelefonoContacto) VALUES(@P1,@P2,'Pendiente',@P3,@P4,@P5,@P6);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarLoteProduccion]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[produccion].[ProduccionLotes] (ProductoID, CantidadProducida) OUTPUT INSERTED.ID VALUES (@P1, @P2);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarInventarioMateriasPrimas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT m.ID, m.Nombre, u.Nombre AS Unidad, m.StockActual, m.StockMinimo FROM[produccion].[MateriaPrima] m JOIN[catalogo].[UnidadesMedida] u ON m.UnidadMedidaID = u.ID ORDER BY m.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarMermasAdmin]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100 m.ID, p.Nombre AS Producto, m.Cantidad, m.Motivo, 
               m.Observaciones, u.NombreCompleto AS RegistradoPor, m.Fecha
        FROM[produccion].[Mermas] m
        JOIN[catalogo].[Productos] p ON m.ProductoID = p.ID
        JOIN[seguridad].[Usuarios] u ON m.UsuarioID = u.ID
        ORDER BY m.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarProveedoresActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Telefono FROM[produccion].[Proveedores] WHERE Activo = 1 ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarUltimasComprasMP]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50 c.ID, m.Nombre AS Materia, p.Nombre AS Proveedor, c.Cantidad, c.CostoTotal, c.Fecha FROM[produccion].[ComprasMateriaPrima] c JOIN[produccion].[MateriaPrima] m ON c.MateriaPrimaID = m.ID JOIN[produccion].[Proveedores] p ON c.ProveedorID = p.ID ORDER BY c.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarUltimosLotesProduccion]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.Fecha FROM[produccion].[ProduccionLotes] pl JOIN[catalogo].[Productos] p ON pl.ProductoID = p.ID ORDER BY pl.Fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarUnidadesMedida]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Abreviatura FROM[catalogo].[UnidadesMedida] ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerEncargoPorCodigoBloqueo]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Lock invoice first, just as the annulment path does, before locking the order.
    DECLARE @FacturaID INT;
    SELECT @FacturaID=ID FROM [ventas].[Facturas] WITH(UPDLOCK,HOLDLOCK) WHERE CodigoSeguimiento=@P1;
    SELECT e.Estado, f.ID, f.NumeroFactura, f.Total, f.EstadoFiscal
      FROM [ventas].[Facturas] f WITH(UPDLOCK,HOLDLOCK)
      JOIN [ventas].[Encargos] e WITH(UPDLOCK,HOLDLOCK) ON f.ID=e.FacturaID WHERE f.ID=@FacturaID;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerMateriaPrimaBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[produccion].[MateriaPrima] WITH (UPDLOCK, HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerMaterialesRequeridosLote]
    @P1 DECIMAL(38, 19) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT m.ID, m.Nombre, m.StockActual, (r.CantidadNecesaria * @P1) AS Requerido
            FROM[produccion].[RecetaProducto] r
            JOIN[produccion].[MateriaPrima] m WITH (UPDLOCK,HOLDLOCK) ON r.MateriaPrimaID = m.ID
            WHERE r.ProductoID = @P2;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerMateriasPrimasConUnidad]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT m.ID, m.Nombre, u.Abreviatura FROM[produccion].[MateriaPrima] m JOIN[catalogo].[UnidadesMedida] u ON m.UnidadMedidaID = u.ID ORDER BY m.Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_SumarStockMateriaPrima]
    @P1 DECIMAL(38, 19) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[produccion].[MateriaPrima] SET StockActual = StockActual + @P1 WHERE ID = @P2;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_VerificarProveedorActivo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[produccion].[Proveedores] WHERE ID=@P1 AND Activo=1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_VerificarUnidadMedidaExiste]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[catalogo].[UnidadesMedida] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarDescriptorFacialEmpleado]
    @P1 NVARCHAR(MAX) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Empleados] SET FaceDescriptor = @P1 WHERE ID = @P2;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarEntradaAsistenciaConUsuario]
    @P1 TIME(7) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 INT = NULL,
    @P5 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Asistencia] SET HoraEntrada = @P1, EstadoEntrada = @P2, TurnoID = @P3, RegistradoPor = @P4
                    WHERE ID = @P5;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarEntradaAsistenciaKiosco]
    @P1 TIME(7) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Asistencia] SET HoraEntrada = @P1, EstadoEntrada = @P2, TurnoID = @P3 WHERE ID = @P4;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarHorarioEmpleado]
    @P1 TIME(7) = NULL,
    @P2 TIME(7) = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Empleados] SET HoraEntrada = @P1, HoraSalida = @P2 WHERE ID = @P3;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarSalidaAsistenciaKiosco]
    @P1 TIME(7) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Asistencia] SET HoraSalida = @P1 WHERE ID = @P2 AND HoraSalida IS NULL;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarSalidaAsistenciaPorID]
    @P1 TIME(7) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[rrhh].[Asistencia] SET HoraSalida = @P1 WHERE ID = @P2;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_AlertasContratosPorVencer]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT NombreCompleto, FechaFinContrato, TipoContrato
        FROM[rrhh].[Empleados]
        WHERE EstadoEmpleado = 'Activo' 
          AND TipoContrato = 'Determinado'
          AND FechaFinContrato IS NOT NULL
          AND FechaFinContrato BETWEEN GETDATE() AND DATEADD(day, 30, GETDATE());
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_AlertasCumpleanosProximos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT NombreCompleto, FechaNacimiento
        FROM[rrhh].[Empleados]
        WHERE EstadoEmpleado = 'Activo' AND FechaNacimiento IS NOT NULL
          AND DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()), FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE())
           OR DATEADD(year, DATEDIFF(year, FechaNacimiento, GETDATE()) + 1, FechaNacimiento) 
              BETWEEN GETDATE() AND DATEADD(day, 15, GETDATE());
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ContarAsistenciasRango]
    @P1 DATE = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) FROM[rrhh].[Asistencia] WHERE Fecha BETWEEN @P1 AND @P2;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ContarEmpleadosActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) FROM[rrhh].[Empleados] WHERE EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_CrearEmpleado]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 DATE = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 NVARCHAR(300) = NULL,
    @P6 NVARCHAR(255) = NULL,
    @P7 NVARCHAR(255) = NULL,
    @P8 NVARCHAR(255) = NULL,
    @P9 NVARCHAR(255) = NULL,
    @P10 DATE = NULL,
    @P11 NVARCHAR(255) = NULL,
    @P12 DATE = NULL,
    @P13 NVARCHAR(255) = NULL,
    @P14 DECIMAL(18, 2) = NULL,
    @P15 NVARCHAR(255) = NULL,
    @P16 BIT = NULL,
    @P17 NVARCHAR(255) = NULL,
    @P18 TIME(7) = NULL,
    @P19 TIME(7) = NULL,
    @P20 NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Empleados] (NombreCompleto, Cedula, FechaNacimiento, Genero, Direccion,
                Telefono, CorreoElectronico, NumeroINSS, Cargo, FechaIngreso, TipoContrato, FechaFinContrato,
                TipoJornada, SalarioBase, FormaPago, ConsentimientoDatos, FechaConsentimiento, FotoPerfil, HoraEntrada, HoraSalida, FaceDescriptor)
            OUTPUT INSERTED.ID
            VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, @P8, @P9, @P10, @P11, @P12, @P13, @P14, @P15, @P16, GETDATE(), @P17, @P18, @P19, @P20);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarAguinaldoBatch]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Nomina] (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                        HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                        INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                        TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                OUTPUT INSERTED.ID
                    VALUES (@P1, @P2, @P3, 0, 0, 0, @P4, @P5, 0, 0, 0, 0, 0, @P6, 0, 0, 'Contabilizada', @P7);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarDeduccionJudicial]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL,
    @P6 NVARCHAR(255) = NULL,
    @P7 DATE = NULL,
    @P8 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[DeduccionesJudiciales] (EmpleadoID,TipoDeduccion,Beneficiario,PorcentajeSalarioNeto,MontoFijo,NumeroJuzgado,FechaInicio,FechaFin) VALUES (@P1,@P2,@P3,@P4,@P5,@P6,@P7,@P8);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarEntradaAsistenciaConUsuario]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DATE = NULL,
    @P4 TIME(7) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Asistencia] (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor)
                    VALUES (@P1, @P2, @P3, @P4, @P5, @P6);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarEntradaAsistenciaKiosco]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DATE = NULL,
    @P4 TIME(7) = NULL,
    @P5 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Asistencia] (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor) VALUES (@P1, @P2, @P3, @P4, @P5, NULL);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarIncidenteLaboral]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 NVARCHAR(MAX) = NULL,
    @P5 DATETIME2 = NULL,
    @P6 BIT = NULL,
    @P7 DATETIME2 = NULL,
    @P8 NVARCHAR(MAX) = NULL,
    @P9 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[IncidentesLaborales] (EmpleadoID,TipoIncidente,Gravedad,Descripcion,FechaIncidente,NotificadoMITRAB,FechaNotificacionMITRAB,AccionesCorrectivas,RegistradoPor) VALUES (@P1,@P2,@P3,@P4,@P5,@P6,@P7,@P8,@P9);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarNominaBatch]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DECIMAL(18, 2) = NULL,
    @P8 DECIMAL(18, 2) = NULL,
    @P9 DECIMAL(18, 2) = NULL,
    @P10 DECIMAL(18, 2) = NULL,
    @P11 DECIMAL(18, 2) = NULL,
    @P12 DECIMAL(18, 2) = NULL,
    @P13 DECIMAL(18, 2) = NULL,
    @P14 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Nomina] (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                    HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                    INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                    TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                OUTPUT INSERTED.ID
                VALUES (@P1, @P2, @P3, @P4, 0, 0, 0, @P5, @P6, @P7, @P8, @P9, @P10, @P11, @P12, @P13, 'Contabilizada', @P14);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarNominaMensual]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DECIMAL(18, 2) = NULL,
    @P8 DECIMAL(18, 2) = NULL,
    @P9 DECIMAL(18, 2) = NULL,
    @P10 DECIMAL(18, 2) = NULL,
    @P11 DECIMAL(18, 2) = NULL,
    @P12 DECIMAL(18, 2) = NULL,
    @P13 DECIMAL(18, 2) = NULL,
    @P14 DECIMAL(18, 2) = NULL,
    @P15 DECIMAL(18, 2) = NULL,
    @P16 DECIMAL(18, 2) = NULL,
    @P17 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[rrhh].[Nomina] (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
            OUTPUT INSERTED.ID
            VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, @P8, @P9, @P10, @P11, @P12, @P13, @P14, @P15, @P16, 'Contabilizada', @P17);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarDeduccionesJudiciales]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT d.ID, d.EmpleadoID, e.NombreCompleto, d.TipoDeduccion, d.Beneficiario, d.PorcentajeSalarioNeto, d.MontoFijo, d.NumeroJuzgado, d.FechaInicio, d.FechaFin, d.Activa FROM[rrhh].[DeduccionesJudiciales] d JOIN[rrhh].[Empleados] e ON e.ID=d.EmpleadoID ORDER BY d.Activa DESC, d.ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEmpleadosActivosBasico]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, Cargo FROM[rrhh].[Empleados] WHERE EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEmpleadosActivosCompletos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM[rrhh].[Empleados] WHERE EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEmpleadosConUsuario]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT e.*, u.Username 
        FROM[rrhh].[Empleados] e 
        LEFT JOIN[seguridad].[Usuarios] u ON e.UsuarioID = u.ID
        ORDER BY e.NombreCompleto;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarIncidentesLaborales]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT i.ID, i.EmpleadoID, e.NombreCompleto, i.TipoIncidente, i.Gravedad, i.Descripcion, i.FechaIncidente, i.NotificadoMITRAB, i.AccionesCorrectivas FROM[rrhh].[IncidentesLaborales] i JOIN[rrhh].[Empleados] e ON e.ID=i.EmpleadoID ORDER BY i.FechaIncidente DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarNominasRecientes]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50 n.ID, e.NombreCompleto, e.Cargo, n.PeriodoInicio, n.PeriodoFin,
               n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto,
               n.INSSPatronal, n.INATEC, n.Estado,
               n.SalarioBruto, n.OtrosIngresos,
               a.ID AS AsientoID, a.NumeroComprobante
        FROM[rrhh].[Nomina] n
        JOIN[rrhh].[Empleados] e ON n.EmpleadoID = e.ID
        OUTER APPLY (
            SELECT TOP 1 ID, NumeroComprobante
            FROM [contabilidad].[AsientosDiario]
            WHERE ReferenciaExterna = CONCAT('NOM-', n.ID)
              AND Estado = 'Contabilizado'
            ORDER BY ID DESC
        ) a
        ORDER BY CASE WHEN n.SalarioBruto > 0 THEN 0 ELSE 1 END,
                 n.PeriodoFin DESC,
                 n.ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ContabilidadNominaMes]
    @Mes INT = NULL,
    @Anio INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ISNULL(SUM(TotalDevengado), 0) AS TotalDevengado,
        ISNULL(SUM(SalarioNeto), 0) AS TotalSalarioNeto,
        ISNULL(SUM(INSSLaboral), 0) AS TotalINSSLaboral,
        ISNULL(SUM(INSSPatronal), 0) AS TotalINSSPatronal,
        ISNULL(SUM(INATEC), 0) AS TotalINATEC,
        ISNULL(SUM(IRMensual), 0) AS TotalIR,
        ISNULL(SUM(TotalDevengado + INSSPatronal + INATEC), 0) AS CostoTotalPlanilla,
        COUNT(*) AS CantidadNominas
    FROM [rrhh].[Nomina]
    WHERE MONTH(PeriodoInicio) = @Mes
      AND YEAR(PeriodoInicio) = @Anio
      AND SalarioBruto > 0
      AND Estado IN ('Contabilizada', 'Pagada');
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarNominasContabilizadasMes]
    @Mes INT = NULL,
    @Anio INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 30 n.ID, e.NombreCompleto, e.Cargo, n.PeriodoInicio, n.PeriodoFin,
           n.TotalDevengado, n.TotalDeducciones, n.SalarioNeto,
           n.INSSLaboral, n.INSSPatronal, n.INATEC, n.IRMensual,
           (n.TotalDevengado + n.INSSPatronal + n.INATEC) AS CostoTotal,
           n.Estado, n.SalarioBruto, n.OtrosIngresos,
           a.ID AS AsientoID, a.NumeroComprobante
    FROM [rrhh].[Nomina] n
    JOIN [rrhh].[Empleados] e ON n.EmpleadoID = e.ID
    OUTER APPLY (
        SELECT TOP 1 ID, NumeroComprobante
        FROM [contabilidad].[AsientosDiario]
        WHERE ReferenciaExterna = CONCAT('NOM-', n.ID)
          AND Estado = 'Contabilizado'
        ORDER BY ID DESC
    ) a
    WHERE ((MONTH(n.PeriodoInicio) = @Mes AND YEAR(n.PeriodoInicio) = @Anio) OR @Mes IS NULL)
      AND n.Estado IN ('Contabilizada', 'Pagada')
    ORDER BY n.PeriodoFin DESC, n.ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerNominaPorIDParaContabilizar]
    @NominaID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT n.ID, n.EmpleadoID, e.NombreCompleto, e.Cargo, e.SalarioBase, e.UsuarioID,
           n.PeriodoInicio, n.PeriodoFin, n.SalarioBruto, n.HorasExtras, n.MontoHorasExtras,
           n.OtrosIngresos, n.TotalDevengado, n.INSSLaboral, n.IRMensual,
           n.PensionAlimenticia, n.ValesDescontados, n.TotalDeducciones,
           n.SalarioNeto, n.INSSPatronal, n.INATEC, n.Estado
    FROM [rrhh].[Nomina] n WITH (UPDLOCK, HOLDLOCK)
    JOIN [rrhh].[Empleados] e ON n.EmpleadoID = e.ID
    WHERE n.ID = @NominaID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_MarcarNominaContabilizada]
    @NominaID INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[Nomina]
    SET Estado = 'Contabilizada'
    WHERE ID = @NominaID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerAsistenciaConTurnoPorFecha]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, t.Nombre AS Turno
            FROM[rrhh].[Asistencia] a
            LEFT JOIN[rrhh].[TurnosLaborales] t ON a.TurnoID = t.ID
            WHERE a.Fecha = @P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, HoraEntrada, HoraSalida FROM[rrhh].[Asistencia] WITH (UPDLOCK, HOLDLOCK) WHERE EmpleadoID = @P1 AND Fecha = @P2;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerAsistenciaPorFechaMonitor]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT a.EmpleadoID, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada, e.NombreCompleto, e.Cargo
        FROM[rrhh].[Asistencia] a 
        JOIN[rrhh].[Empleados] e ON a.EmpleadoID = e.ID
        WHERE a.Fecha = @P1
        ORDER BY a.HoraEntrada DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerColillaNominaPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT n.*, e.NombreCompleto, e.Cargo, e.Cedula, e.NumeroINSS, e.FechaIngreso
        FROM[rrhh].[Nomina] n
        JOIN[rrhh].[Empleados] e ON n.EmpleadoID = e.ID
        WHERE n.ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerDeduccionesJudicialesVigentes]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT PorcentajeSalarioNeto, MontoFijo FROM[rrhh].[DeduccionesJudiciales] WHERE EmpleadoID=@P1 AND Activa=1 AND FechaInicio<=@P2 AND (FechaFin IS NULL OR FechaFin>=@P3);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoActivoCompleto]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM[rrhh].[Empleados] WHERE ID = @P1 AND EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto FROM[rrhh].[Empleados] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @P1 AND EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[rrhh].[Empleados] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoCompletoPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM[rrhh].[Empleados] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoKioscoPorCedulaBloqueo]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM[rrhh].[Empleados] WITH (UPDLOCK, HOLDLOCK) WHERE Cedula = @P1 AND EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoKioscoPorIDBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM[rrhh].[Empleados] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @P1 AND EstadoEmpleado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadosReferenciasFoto]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, FotoPerfil FROM[rrhh].[Empleados] WHERE EstadoEmpleado = 'Activo' AND FotoPerfil IS NOT NULL;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerFechasAsistidasEmpleado]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DISTINCT Fecha FROM[rrhh].[Asistencia] WHERE EmpleadoID = @P1 AND Fecha BETWEEN @P2 AND @P3 AND HoraEntrada IS NOT NULL;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerFechasIngresoEgresoEmpleado]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT FechaIngreso, FechaEgreso FROM[rrhh].[Empleados] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerLicenciasSolapadasEmpleado]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT FechaInicio, FechaFin, TipoLicencia FROM[rrhh].[LicenciasEmpleados] WHERE EmpleadoID = @P1 AND FechaInicio <= @P2 AND FechaFin >= @P3;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerTurnoLaboralActivoDefecto]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos FROM[rrhh].[TurnosLaborales] WHERE Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerUltimos6SalariosHastaFecha]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 6 SalarioBruto FROM[rrhh].[Nomina] WHERE EmpleadoID = @P1 AND PeriodoFin <= @P2 ORDER BY PeriodoFin DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerUltimos6SalariosNomina]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 6 SalarioBruto FROM[rrhh].[Nomina] WHERE EmpleadoID = @P1 ORDER BY PeriodoFin DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerVacacionesEmpleadoRango]
    @P1 INT = NULL,
    @P2 DATE = NULL,
    @P3 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT FechaInicio, FechaFin, TipoLicencia, DiasOtorgados FROM[rrhh].[LicenciasEmpleados] WHERE EmpleadoID = @P1 AND TipoLicencia = 'Vacaciones' AND FechaInicio <= @P2 AND FechaFin >= @P3;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ReporteAguinaldoAnio]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT e.NombreCompleto, e.Cedula, e.FechaIngreso, n.PeriodoFin, n.OtrosIngresos AS AguinaldoMonto
        FROM[rrhh].[Nomina] n
        JOIN[rrhh].[Empleados] e ON n.EmpleadoID = e.ID
        WHERE YEAR(n.PeriodoFin) = @P1 AND n.SalarioBruto = 0 AND n.OtrosIngresos > 0
        ORDER BY e.NombreCompleto;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ReporteINSSPatronalMesAnio]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT e.NombreCompleto, e.NumeroINSS, n.TotalDevengado, n.INSSLaboral, n.INSSPatronal, n.INATEC
        FROM[rrhh].[Nomina] n
        JOIN[rrhh].[Empleados] e ON n.EmpleadoID = e.ID
        WHERE MONTH(n.PeriodoInicio) = @P1 AND YEAR(n.PeriodoInicio) = @P2;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_SuspenderEmpleado]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[rrhh].[Empleados] SET EstadoEmpleado='Suspendido' WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_VerificarEmpleadoExiste]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[rrhh].[Empleados] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActivarTOTPUsuario]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[seguridad].[Usuarios] SET TOTPSecret = @P1, TOTPEnabled = 1 WHERE ID = @P2;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarConfiguracionClaveExistente]
    @P1 NVARCHAR(MAX) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[seguridad].[ConfiguracionSistema] SET Valor=@P1 WHERE Clave=@P2;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarConfiguracionClaveValor]
    @P1 NVARCHAR(MAX) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[seguridad].[ConfiguracionSistema] SET Valor=@P1 WHERE Clave=@P2;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ConsumirDesafiosFamilia]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[seguridad].[AuthChallenges] SET Consumed = 1 WHERE Subject = @P1 AND Kind LIKE @P2;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_IncrementarIntentosDesafio]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[seguridad].[AuthChallenges] SET Attempts = Attempts + 1 WHERE Token = @P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_InsertarUsuario]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[seguridad].[Usuarios] (NombreCompleto, Username, PasswordHash, RolID, Activo) OUTPUT INSERTED.ID VALUES (@P1, @P2, @P3, @P4, 1);
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarUsuariosActivosSimple]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto FROM[seguridad].[Usuarios] WHERE Activo = 1 ORDER BY NombreCompleto;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ListarUsuariosTOTP]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT u.ID, u.NombreCompleto, u.Username, r.Nombre AS Rol, u.TOTPEnabled FROM[seguridad].[Usuarios] u JOIN[seguridad].[Roles] r ON u.RolID = r.ID WHERE u.Activo = 1 ORDER BY u.NombreCompleto;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_MarcarDesafioVerificado]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE[seguridad].[AuthChallenges] SET Verified = 1 WHERE Token = @P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerConfiguracionGlobal]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Clave, Valor FROM[seguridad].[ConfiguracionSistema];
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerEstadoUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT NombreCompleto, Username, RolID, Activo FROM[seguridad].[Usuarios] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerMaxExpiracionDesafioSMS]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT MAX(ExpiresAt) FROM[seguridad].[AuthChallenges] WITH (UPDLOCK, HOLDLOCK) WHERE Subject = @P1 AND Kind = @P2;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerNombreUsuarioPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT NombreCompleto FROM[seguridad].[Usuarios] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerPerfilDGI]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Clave,Valor FROM[seguridad].[ConfiguracionSistema] WHERE Clave LIKE 'fiscal[_]%' OR Clave LIKE 'dgi[_]%' ORDER BY Clave;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerRolPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Nombre FROM[seguridad].[Roles] WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerRolUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT r.Nombre FROM[seguridad].[Usuarios] u JOIN[seguridad].[Roles] r ON r.ID=u.RolID WHERE u.ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerTOTPActivoUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOTPSecret, TOTPEnabled FROM[seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @P1 AND Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerTasasLaboralesConfig]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Clave, Valor FROM[seguridad].[ConfiguracionSistema] WHERE Clave IN ('inss_laboral', 'inss_patronal_menos50', 'inss_patronal_mas50', 'inatec', 'ir_tabla');
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_RevocarDesafioPorToken]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[seguridad].[AuthChallenges] SET Consumed = 1 WHERE Token = @P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ToggleActivoUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[seguridad].[Usuarios] SET Activo = 1 ^ Activo WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarRolUsuario]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [seguridad].[Usuarios]
    SET RolID = @P2
    WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ActualizarDocumentoJSONFactura]
    @P1 NVARCHAR(MAX) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[ventas].[Facturas] SET DocumentoJSON=@P1 WHERE ID=@P2;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_AdquirirLockFactura]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @r INT; EXEC @r=sp_getapplock @Resource=@P1,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @r;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_AgruparPagosPorMetodoFactura]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT MetodoPago,SUM(Monto) FROM[ventas].[Pagos] WHERE FacturaID=@P1 GROUP BY MetodoPago;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_CalcularValoresSistemaTurno]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM [ventas].[Pagos] p JOIN [ventas].[Facturas] f ON f.ID=p.FacturaID
               JOIN [ventas].[TurnosCaja] t ON t.ID=@P1
               WHERE p.Monto<>0 AND (p.TurnoReceptorID IS NULL OR p.UsuarioReceptorID IS NULL)
                 AND (f.TurnoID=@P1 OR (p.FechaPago>=t.FechaApertura AND (t.FechaCierre IS NULL OR p.FechaPago<=t.FechaCierre))))
        THROW 51021, 'Existen movimientos históricos sin receptor de caja. Conciliar antes del arqueo.', 1;
    SELECT
                ISNULL(SUM(CASE WHEN (p.MetodoPago = 'Efectivo' OR (p.MetodoPago='Efectivo USD' AND p.MonedaRegistro='NIO')) THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' AND p.MonedaRegistro<>'NIO' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
                ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
            FROM[ventas].[Pagos] p
            WHERE p.TurnoReceptorID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_CerrarTurnoCajaEnArqueo]
    @P1 DECIMAL(18, 2) = NULL,
    @P2 DECIMAL(18, 2) = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[ventas].[TurnosCaja] SET Cerrado = 1, FechaCierre = GETDATE(),
                EfectivoCalculado = @P1, TransferenciasCalculadas = @P2, TotalVentaNeta = @P3
            WHERE ID = @P4;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ContabilidadIngresosDia]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Total), 0) FROM[ventas].[Facturas] WHERE EstadoFiscal='Emitida' AND CONVERT(date, FechaHora) = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ContabilidadIngresosMes]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Total), 0) FROM[ventas].[Facturas] WHERE EstadoFiscal='Emitida' AND MONTH(FechaHora) = @P1 AND YEAR(FechaHora) = @P2;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_DashboardIngresosHoy]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Total), 0), ISNULL(COUNT(ID), 0) FROM[ventas].[Facturas] WHERE EstadoFiscal='Emitida' AND CONVERT(date, FechaHora) = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_DashboardTopProductosHoy]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 5 p.Nombre, SUM(df.Cantidad) as Cantidad FROM[ventas].[DetalleFacturas] df JOIN[catalogo].[Productos] p ON df.ProductoID = p.ID JOIN[ventas].[Facturas] f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida' WHERE CONVERT(date, f.FechaHora) = @P1 GROUP BY p.Nombre ORDER BY Cantidad DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_DashboardTurnosActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT t.ID, u.NombreCompleto, t.FechaApertura FROM[ventas].[TurnosCaja] t JOIN[seguridad].[Usuarios] u ON t.UsuarioID = u.ID WHERE t.Cerrado = 0;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_DashboardVentasCategoriaHoy]
    @P1 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.Nombre, SUM(df.Subtotal) as TotalGenerado FROM[ventas].[DetalleFacturas] df JOIN[catalogo].[Productos] p ON df.ProductoID = p.ID JOIN[catalogo].[Categorias] c ON p.CategoriaID = c.ID JOIN[ventas].[Facturas] f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida' WHERE CONVERT(date, f.FechaHora) = @P1 GROUP BY c.Nombre ORDER BY TotalGenerado DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaArqueosRecientes]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 10 a.ID, u.NombreCompleto, a.EfectivoContado, a.EfectivoSistema,
               a.DiferenciaEfectivo, a.DiferenciaTransferencias, a.FechaArqueo
        FROM[ventas].[ArqueoCaja] a
        JOIN[seguridad].[Usuarios] u ON a.UsuarioID = u.ID
        ORDER BY a.FechaArqueo DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaHistoricoVentasRegresion]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CONVERT(date, FechaHora) AS Dia, ISNULL(SUM(Total), 0) AS Total
        FROM[ventas].[Facturas]
        WHERE EstadoFiscal='Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaRotacionProductos30d]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 15 p.Nombre, SUM(df.Cantidad) AS Vendidos, SUM(df.Subtotal) AS Ingresos
        FROM[ventas].[DetalleFacturas] df
        JOIN[catalogo].[Productos] p ON df.ProductoID = p.ID
        JOIN[ventas].[Facturas] f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida'
        WHERE f.FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre
        ORDER BY Vendidos DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaVentasDiarias30d]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CONVERT(date, FechaHora) AS Dia, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM[ventas].[Facturas]
        WHERE EstadoFiscal='Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaVentasPorHora]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DATEPART(HOUR, FechaHora) AS Hora, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM[ventas].[Facturas]
        WHERE EstadoFiscal='Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY DATEPART(HOUR, FechaHora)
        ORDER BY Hora;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticasResumenArqueos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
            COUNT(*) AS Total,
            SUM(CASE WHEN ABS(DiferenciaEfectivo) + ABS(DiferenciaTransferencias) < 1 THEN 1 ELSE 0 END) AS Cuadrados,
            SUM(CASE WHEN DiferenciaEfectivo > 0 THEN 1 ELSE 0 END) AS Sobrantes,
            SUM(CASE WHEN DiferenciaEfectivo < 0 THEN 1 ELSE 0 END) AS Faltantes,
            ISNULL(AVG(ABS(DiferenciaEfectivo)), 0) AS PromDiferencia
        FROM[ventas].[ArqueoCaja]
        WHERE FechaArqueo >= DATEADD(DAY, -30, GETDATE());
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ExportarFacturasRangoFiscal]
    @P1 DATETIME2 = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT NumeroFactura,FechaHora,Subtotal,IVA,Total,EstadoFiscal,FechaAnulacion,MotivoAnulacion FROM[ventas].[Facturas] WHERE FechaHora>=@P1 AND FechaHora<DATEADD(day,1,CAST(@P2 AS date)) ORDER BY ID;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarArqueoDenominacion]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[ArqueoDetalleDenominacion] (ArqueoID, TipoMoneda, Denominacion, Cantidad)
                    VALUES (@P1, @P2, @P3, @P4);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarArqueoEtapa1]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL,
    @P6 DECIMAL(18, 6) = NULL,
    @P7 DECIMAL(18, 2) = NULL,
    @P8 DECIMAL(18, 2) = NULL,
    @P9 DECIMAL(18, 2) = NULL,
    @P10 DECIMAL(18, 2) = NULL,
    @P11 NVARCHAR(500) = NULL,
    @P12 BIT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[ArqueoCaja] (TurnoID, UsuarioID, EfectivoContado, TransferenciasContadas,
                DolaresContados, TipoCambioUsado, EfectivoSistema, TransferenciasSistema,
                DiferenciaEfectivo, DiferenciaTransferencias, Observaciones,
                EstadoArqueo, RequiereJustificacion)
            OUTPUT INSERTED.ID
            VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, @P8, @P9, @P10, @P11, 'Pendiente', @P12);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarDetalleFactura]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 INT = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 DECIMAL(18, 2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[DetalleFacturas](FacturaID,ProductoID,Cantidad,PrecioUnitario,Subtotal) OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3,@P4,@P5);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarDetalleIngrediente]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[DetalleIngredientes](DetalleFacturaID,IngredienteID,PrecioAplicado) VALUES(@P1,@P2,@P3);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarFacturaCabecera]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 INT = NULL,
    @P5 INT = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DECIMAL(18, 2) = NULL,
    @P8 DECIMAL(18, 2) = NULL,
    @P9 BIT = NULL,
    @P10 BIT = NULL,
    @P11 NVARCHAR(255) = NULL,
    @P12 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[Facturas](NumeroFactura,CodigoSeguimiento,UsuarioID,ClienteID,TurnoID,Subtotal,IVA,Total,EsEncargo,IncluyeRUC,ClaveSolicitud,FechaHora) OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3,@P4,@P5,@P6,@P7,@P8,@P9,@P10,@P11,@P12);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarFacturaRUC]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[FacturasRUC](FacturaID,RazonSocial,NumeroRUC) VALUES(@P1,@P2,@P3);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarPagoDevolucionAnulacion]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @TurnoID INT, @UsuarioID INT=TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
    SELECT @TurnoID=TurnoID FROM [ventas].[Facturas] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
    IF @UsuarioID IS NULL OR NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@TurnoID AND Cerrado=0)
        THROW 51023, 'La devolución requiere usuario identificado y caja abierta.', 1;
    INSERT INTO[ventas].[Pagos](FacturaID,MetodoPago,Monto,NombreTransferente,MonedaRegistro,TurnoReceptorID,UsuarioReceptorID) VALUES(@P1,@P2,@P3,@P4,'NIO',@TurnoID,@UsuarioID);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarPagoFactura]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 DECIMAL(18, 6) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @TurnoID INT, @UsuarioID INT, @FechaPago DATETIME2;
    SELECT @TurnoID=TurnoID,@UsuarioID=UsuarioID,@FechaPago=FechaHora FROM [ventas].[Facturas] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1 AND EstadoFiscal='Emitida';
    IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@TurnoID AND UsuarioID=@UsuarioID AND Cerrado=0)
        THROW 51024, 'El pago inicial requiere la caja abierta del emisor.', 1;
    INSERT INTO[ventas].[Pagos](FacturaID,MetodoPago,Monto,NombreTransferente,MonedaRegistro,TipoCambioAplicado,TurnoReceptorID,UsuarioReceptorID,FechaPago) VALUES(@P1,@P2,@P3,@P4,'NIO',@P5,@TurnoID,@UsuarioID,@FechaPago);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarPagoSaldoEncargo]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 NVARCHAR(255) = NULL,
    @P5 DATETIME2 = NULL,
    @P6 DECIMAL(18, 6) = NULL,
    @TurnoReceptorID INT = NULL,
    @UsuarioReceptorID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Defaults preserve the old call shape without guessing a receiving identity.
    SET @UsuarioReceptorID=COALESCE(@UsuarioReceptorID,TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT));
    IF NOT EXISTS (SELECT 1 FROM [ventas].[Facturas] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1 AND EstadoFiscal='Emitida')
        THROW 51025, 'La factura no está emitida.', 1;
    IF @TurnoReceptorID IS NULL
        SELECT TOP 1 @TurnoReceptorID=ID FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK)
        WHERE UsuarioID=@UsuarioReceptorID AND Cerrado=0 ORDER BY ID DESC;
    IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@TurnoReceptorID AND UsuarioID=@UsuarioReceptorID AND Cerrado=0)
        THROW 51026, 'El saldo requiere la caja abierta del usuario receptor.', 1;
    IF EXISTS (SELECT 1 FROM [ventas].[ArqueoCaja] WHERE TurnoID=@TurnoReceptorID AND EstadoArqueo IN ('Pendiente','Verificado'))
        THROW 51027, 'La caja receptora tiene un arqueo pendiente.', 1;
    INSERT INTO[ventas].[Pagos] (FacturaID, MetodoPago, Monto, NombreTransferente, FechaPago, MonedaRegistro, TipoCambioAplicado,TurnoReceptorID,UsuarioReceptorID) VALUES (@P1, @P2, @P3, @P4, @P5, 'NIO', @P6,@TurnoReceptorID,@UsuarioReceptorID);
END
GO

-- Explicit, audited reconciliation of legacy movement attribution; never bulk infer it.
CREATE OR ALTER PROCEDURE [ventas].[sp_RegistrarEventoFiscalOperacion]
    @UsuarioID INT, @Accion NVARCHAR(50), @Entidad NVARCHAR(50),
    @EntidadID INT=NULL, @Detalle NVARCHAR(MAX), @IP VARCHAR(45)=NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Restricted business roles can only append their own invoice operation events.
    IF IS_MEMBER('db_rol_produccion')=1 OR IS_MEMBER('db_rol_cajero_pos')=1
    BEGIN
        IF @Entidad<>N'Factura' OR @EntidadID IS NULL OR @UsuarioID<>TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT)
           OR TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT) IS NULL
           OR NOT EXISTS (SELECT 1 FROM [ventas].[Facturas] WHERE ID=@EntidadID)
            THROW 51033, 'Evento fiscal operativo no autorizado.', 1;
        IF @Accion<>N'ESTADO_ENCARGO' AND NOT (IS_MEMBER('db_rol_cajero_pos')=1 AND @Accion=N'EMISION')
            THROW 51033, 'Evento fiscal operativo no autorizado.', 1;
    END
    EXEC [fiscal].[sp_RegistrarBitacoraFiscal] @UsuarioID,@Accion,@Entidad,@EntidadID,@Detalle,@IP;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ConciliarReceptorPagoHistorico]
    @PagoID INT, @TurnoID INT, @UsuarioReceptorID INT,
    @UsuarioConciliadorID INT, @Evidencia NVARCHAR(1000)
AS
BEGIN
    SET NOCOUNT ON;
    IF ISNULL(IS_MEMBER('db_rol_gerencia'),0)<>1 AND ISNULL(IS_MEMBER('db_rol_superadmin'),0)<>1 AND ISNULL(IS_MEMBER('db_owner'),0)<>1
        THROW 51028, 'La conciliación histórica requiere Admin o SuperAdmin.', 1;
    IF LEN(LTRIM(RTRIM(ISNULL(@Evidencia,N''))))<15
        THROW 51029, 'Indique evidencia del recibo y la caja receptora.', 1;
    IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@TurnoID AND UsuarioID=@UsuarioReceptorID)
        THROW 51030, 'La caja no pertenece al usuario receptor indicado.', 1;
    IF NOT EXISTS (SELECT 1 FROM [ventas].[Pagos] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@PagoID AND TurnoReceptorID IS NULL AND UsuarioReceptorID IS NULL)
        THROW 51031, 'El pago no existe o ya tiene receptor confirmado.', 1;
    DECLARE @Detalle NVARCHAR(MAX)=(SELECT @TurnoID AS turno_receptor,@UsuarioReceptorID AS usuario_receptor,@Evidencia AS evidencia FOR JSON PATH,WITHOUT_ARRAY_WRAPPER);
    EXEC [fiscal].[sp_RegistrarBitacoraFiscal] @UsuarioConciliadorID,N'CONCILIAR_RECEPTOR_PAGO',N'Pagos',@PagoID,@Detalle,NULL;
    UPDATE [ventas].[Pagos] SET TurnoReceptorID=@TurnoID,UsuarioReceptorID=@UsuarioReceptorID WHERE ID=@PagoID;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_InsertarTurnoCaja]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO[ventas].[TurnosCaja] (UsuarioID) OUTPUT INSERTED.ID VALUES (@P1);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ListarArqueosAdmin]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 50 a.ID, a.TurnoID, u_cajero.NombreCompleto AS Cajero,
               ISNULL(u_verif.NombreCompleto, '—') AS Verificador,
               a.EfectivoContado, a.EfectivoSistema,
               a.TransferenciasContadas, a.TransferenciasSistema,
               a.DiferenciaEfectivo, a.DiferenciaTransferencias,
               a.DolaresContados, a.TipoCambioUsado,
               a.Observaciones, a.NotasDiscrepancia,
               ISNULL(a.EstadoArqueo, 'Cerrado') AS EstadoArqueo,
               a.FechaArqueo, a.FechaVerificacion,
               ISNULL(a.RequiereJustificacion, 0) AS RequiereJustificacion
        FROM[ventas].[ArqueoCaja] a
        JOIN[seguridad].[Usuarios] u_cajero ON a.UsuarioID = u_cajero.ID
        LEFT JOIN[seguridad].[Usuarios] u_verif ON a.VerificadoPorID = u_verif.ID
        ORDER BY a.FechaArqueo DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ListarUltimasFacturasFiscal]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100 ID,NumeroFactura,FechaHora,Total,EstadoFiscal,DocumentoJSON FROM[ventas].[Facturas] ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [fiscal].[sp_ListarFacturasPeriodo]
    @PeriodoID INT,
    @Buscar NVARCHAR(100) = NULL,
    @Estado NVARCHAR(12) = NULL,
    @EsEncargo BIT = NULL,
    @Desde DATE = NULL,
    @Hasta DATE = NULL,
    @Pagina INT = 1,
    @Tamano INT = 10,
    @RecienteDesde DATETIME = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @Pagina < 1 OR @Tamano NOT IN (10,25,50) OR @PeriodoID < 1
        THROW 51050, 'Parámetros de paginación fiscal inválidos.', 1;
    DECLARE @Inicio DATE, @Fin DATE;
    SELECT @Inicio=Desde, @Fin=Hasta FROM [fiscal].[DGI_Periodos] WHERE ID=@PeriodoID;
    IF @Inicio IS NULL
        THROW 51051, 'Período DGI inexistente.', 1;
    IF @Desde IS NOT NULL AND @Desde > @Inicio SET @Inicio=@Desde;
    IF @Hasta IS NOT NULL AND @Hasta < @Fin SET @Fin=@Hasta;
    DECLARE @FinExclusivo DATE=DATEADD(day,1,@Fin);
    DECLARE @Patron NVARCHAR(220)=NULL;
    IF NULLIF(LTRIM(RTRIM(@Buscar)),N'') IS NOT NULL
        SET @Patron=N'%' + REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(@Buscar)), N'[', N'[[]'), N'%', N'[%]'), N'_', N'[_]') + N'%';

    SELECT COUNT_BIG(*) AS Total
    FROM [ventas].[Facturas] f
    LEFT JOIN [crm].[Clientes] c ON c.ID=f.ClienteID
    LEFT JOIN [ventas].[FacturasRUC] r ON r.FacturaID=f.ID
    WHERE f.FechaHora>=@Inicio AND f.FechaHora<@FinExclusivo
      AND (@Estado IS NULL OR f.EstadoFiscal=@Estado)
      AND (@EsEncargo IS NULL OR f.EsEncargo=@EsEncargo)
      AND (@Patron IS NULL OR f.NumeroFactura LIKE @Patron
           OR c.Nombre LIKE @Patron OR c.Apellidos LIKE @Patron OR r.RazonSocial LIKE @Patron);

    SELECT f.ID, f.NumeroFactura, f.FechaHora, f.Total, f.EstadoFiscal, f.EsEncargo,
           COALESCE(NULLIF(r.RazonSocial,N''), NULLIF(LTRIM(RTRIM(CONCAT(c.Nombre,N' ',c.Apellidos))),N''), N'Consumidor final') AS Cliente,
           CONVERT(bit,CASE WHEN @RecienteDesde IS NOT NULL AND f.FechaHora>=@RecienteDesde
                  AND f.FechaHora<=DATEADD(hour,24,@RecienteDesde) THEN 1 ELSE 0 END) AS EsReciente
    FROM [ventas].[Facturas] f
    LEFT JOIN [crm].[Clientes] c ON c.ID=f.ClienteID
    LEFT JOIN [ventas].[FacturasRUC] r ON r.FacturaID=f.ID
    WHERE f.FechaHora>=@Inicio AND f.FechaHora<@FinExclusivo
      AND (@Estado IS NULL OR f.EstadoFiscal=@Estado)
      AND (@EsEncargo IS NULL OR f.EsEncargo=@EsEncargo)
      AND (@Patron IS NULL OR f.NumeroFactura LIKE @Patron
           OR c.Nombre LIKE @Patron OR c.Apellidos LIKE @Patron OR r.RazonSocial LIKE @Patron)
    ORDER BY f.FechaHora DESC, f.ID DESC
    OFFSET (CONVERT(bigint,@Pagina)-1)*@Tamano ROWS FETCH NEXT @Tamano ROWS ONLY;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_MarcarArqueoCerrado]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[ventas].[ArqueoCaja] SET EstadoArqueo = 'Cerrado' WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_MarcarArqueoVerificado]
    @P1 INT = NULL,
    @P2 NVARCHAR(1000) = NULL,
    @P3 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[ventas].[ArqueoCaja] SET
                VerificadoPorID = @P1,
                FechaVerificacion = GETDATE(),
                EstadoArqueo = 'Verificado',
                NotasDiscrepancia = @P2
            WHERE ID = @P3;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_MarcarFacturaAnulada]
    @P1 INT = NULL,
    @P2 DATETIME2 = NULL,
    @P3 NVARCHAR(300) = NULL,
    @P4 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE[ventas].[Facturas] SET EstadoFiscal='Anulada',AnuladaPor=@P1,FechaAnulacion=@P2,MotivoAnulacion=@P3 WHERE ID=@P4;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerArqueoParaVerificarBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT UsuarioID, RequiereJustificacion, EstadoArqueo FROM[ventas].[ArqueoCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerAuditLogArqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT al.Accion, al.Detalle, u.NombreCompleto, al.FechaAccion
        FROM[ventas].[ArqueoAuditLog] al
        JOIN[seguridad].[Usuarios] u ON al.UsuarioID = u.ID
        WHERE al.ArqueoID = @P1
        ORDER BY al.FechaAccion;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerDenominacionesArqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TipoMoneda, Denominacion, Cantidad, Subtotal
        FROM[ventas].[ArqueoDetalleDenominacion] WHERE ArqueoID = @P1
        ORDER BY TipoMoneda, Denominacion DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerDetallesFuenteFacturaDGI]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT d.ID,p.Nombre AS Producto,d.Cantidad,d.PrecioUnitario,d.Subtotal
                FROM[ventas].[DetalleFacturas] d LEFT JOIN[catalogo].[Productos] p ON p.ID=d.ProductoID WHERE d.FacturaID=@P1 ORDER BY d.ID;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerEstadoCerradoTurnoBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Cerrado FROM[ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerFacturaParaAnularBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT EstadoFiscal,DocumentoJSON,TurnoID,ClienteID FROM[ventas].[Facturas] WITH (UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerFacturaPorClaveSolicitud]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT UsuarioID,DocumentoJSON FROM[ventas].[Facturas] WHERE ClaveSolicitud=@P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerHistorialFacturasCliente]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NumeroFactura, FechaHora, Subtotal, IVA, Total, EstadoFiscal FROM[ventas].[Facturas] WHERE ClienteID = @P1 ORDER BY FechaHora DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerMontosSistemaArqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT EfectivoSistema, TransferenciasSistema FROM[ventas].[ArqueoCaja] WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTotalPagadoFactura]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[ventas].[Pagos] WHERE FacturaID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTotalVentasEmitidasTurno]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Total), 0) FROM[ventas].[Facturas] WHERE EstadoFiscal='Emitida' AND TurnoID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTurnoAbierto]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, FechaApertura FROM[ventas].[TurnosCaja] WHERE UsuarioID = @P1 AND Cerrado = 0 ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTurnoAbiertoBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID FROM[ventas].[TurnosCaja] WITH (UPDLOCK, HOLDLOCK) WHERE UsuarioID = @P1 AND Cerrado = 0 ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTurnoActivoParaVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[ventas].[TurnosCaja] WITH(UPDLOCK,HOLDLOCK) WHERE UsuarioID = @P1 AND Cerrado = 0;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerTurnoIDArqueoBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TurnoID FROM[ventas].[ArqueoCaja] WITH(UPDLOCK,HOLDLOCK) WHERE ID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_SeguimientoAdelantoPublico]
    @P1 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0) FROM[ventas].[Pagos] WHERE FacturaID = (SELECT ID FROM[ventas].[Facturas] WHERE CodigoSeguimiento = @P1);
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_VerificarArqueoPendienteTurno]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID FROM[ventas].[ArqueoCaja] WHERE TurnoID=@P1 AND EstadoArqueo IN ('Pendiente','Verificado');
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_VerificarColumnaEstadoFiscalFacturas]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Facturas' AND COLUMN_NAME = 'EstadoFiscal';
END
GO

-- ============================================================================
-- 9. ASIGNACIÓN GRANULAR DE PERMISOS (GRANT EXECUTE / DENY EXECUTE) POR ROL
-- ============================================================================

-- 9.1 db_rol_superadmin: Acceso completo a todos los Stored Procedures de los 8 esquemas
GRANT EXECUTE ON SCHEMA::[seguridad] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[crm] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[catalogo] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[ventas] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[produccion] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[rrhh] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[contabilidad] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[fiscal] TO [db_rol_superadmin];
GO

-- 9.2 db_rol_gerencia: Acceso ejecutivo/administrativo a los 8 esquemas excepto auditoría global y bitácora técnica
GRANT EXECUTE ON SCHEMA::[crm] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[catalogo] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[ventas] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[produccion] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[rrhh] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[contabilidad] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[fiscal] TO [db_rol_gerencia];
GRANT EXECUTE ON SCHEMA::[seguridad] TO [db_rol_gerencia];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarAuditoria] TO [db_rol_gerencia];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarBitacoraErrores] TO [db_rol_gerencia];
DENY EXECUTE ON OBJECT::[seguridad].[sp_MarcarErrorNotificadoSMTP] TO [db_rol_gerencia];
GO

-- 9.3 db_rol_cajero_pos: Operaciones de POS, turnos, arqueo etapa 1, cotizaciones, monitor y asientos automáticos de venta
DENY EXECUTE ON SCHEMA::[rrhh] TO [db_rol_cajero_pos];
GRANT EXECUTE ON SCHEMA::[catalogo] TO [db_rol_cajero_pos];
GRANT EXECUTE ON SCHEMA::[crm] TO [db_rol_cajero_pos];
GRANT EXECUTE ON SCHEMA::[ventas] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[ventas].[sp_MarcarFacturaAnulada] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[ventas].[sp_ConciliarReceptorPagoHistorico] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[ventas].[sp_MarcarArqueoVerificado] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[ventas].[sp_MarcarArqueoCerrado] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_ListarEncargosMonitor] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_RegistrarMerma] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_InsertarEncargo] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_MonitorEncargosActivos] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_MonitorDetallesEncargosActivos] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_ObtenerEncargoPorCodigoBloqueo] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[produccion].[sp_ActualizarEstadoEncargoCompare] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[produccion].[sp_InsertarCompraMateriaPrima] TO [db_rol_cajero_pos];
-- Clear legacy schema DENY so only the explicit helper grants below become usable.
REVOKE EXECUTE ON SCHEMA::[contabilidad] FROM [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerCuentaActivaPorCodigo] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerPeriodoContablePorMesAnio] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarPeriodoContableAbierto] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_SiguienteNumeroComprobante] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarCabeceraAsiento] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ActualizarEmisorJSONAsiento] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InicializarEmisorYAuditarAsiento] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerEsTransaccionalCuenta] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarLineaDetalleAsiento] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_VerificarCuentaTransaccionalActiva] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerBalanceGeneral] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerBalanceGeneralCorte] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerEstadoResultados] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerEstadoResultadosPeriodo] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_CerrarPeriodoContable] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[fiscal].[sp_RegistrarBitacoraFiscal] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[fiscal].[sp_ListarPeriodosDGI] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[fiscal].[sp_ListarRevisionesDGI] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarErrorBD] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerUsuarioPorID] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_AutenticarUsuario] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionSistema] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionClave] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionGlobal] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerValorConfiguracion] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarAuditoria] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarIntentoLogin] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoCuenta] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LeerDesafioAuth] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerMaxExpiracionDesafioSMS] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ConsumirDesafiosFamilia] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_InsertarDesafioAuth] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RevocarDesafioPorToken] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_IncrementarIntentosDesafio] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_MarcarDesafioVerificado] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerTOTPActivoUsuario] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ActivarTOTPUsuario] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarBitacoraErrores] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarAuditoria] TO [db_rol_cajero_pos];
GO

-- 9.4 db_rol_produccion: Monitor de cocina, recetas, lotes de producción, inventario y mermas
DENY EXECUTE ON SCHEMA::[rrhh] TO [db_rol_produccion];
DENY EXECUTE ON SCHEMA::[fiscal] TO [db_rol_produccion];
DENY EXECUTE ON SCHEMA::[crm] TO [db_rol_produccion];
GRANT EXECUTE ON SCHEMA::[produccion] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerCatalogoActivo] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerProductosParaProduccion] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_VerificarColumnaEstadoFiscalFacturas] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoEncargoPublico] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoAdelantoPublico] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoProductosPublico] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerTotalPagadoFactura] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_RegistrarEventoFiscalOperacion] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[ventas].[sp_InsertarPagoSaldoEncargo] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[ventas].[sp_ListarArqueosCaja] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[ventas].[sp_ListarArqueosAdmin] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[ventas].[sp_RegistrarFacturaCompleta] TO [db_rol_produccion];
-- Narrow journal helpers also support the authorized inventory purchase workflow.
REVOKE EXECUTE ON SCHEMA::[contabilidad] FROM [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerCuentaActivaPorCodigo] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerPeriodoContablePorMesAnio] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarPeriodoContableAbierto] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_SiguienteNumeroComprobante] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarCabeceraAsiento] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ActualizarEmisorJSONAsiento] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InicializarEmisorYAuditarAsiento] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerEsTransaccionalCuenta] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_InsertarLineaDetalleAsiento] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[contabilidad].[sp_VerificarCuentaTransaccionalActiva] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerBalanceGeneral] TO [db_rol_produccion];
DENY EXECUTE ON OBJECT::[contabilidad].[sp_ObtenerBalanceGeneralCorte] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarErrorBD] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerUsuarioPorID] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_AutenticarUsuario] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerValorConfiguracion] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarAuditoria] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarIntentoLogin] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoCuenta] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LeerDesafioAuth] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ConsumirDesafiosFamilia] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_InsertarDesafioAuth] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RevocarDesafioPorToken] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_IncrementarIntentosDesafio] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerTOTPActivoUsuario] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ActivarTOTPUsuario] TO [db_rol_produccion];
GO

-- 9.5 db_rol_kiosco: Exclusivamente lectura de descriptores faciales y registro de asistencia/errores
DENY EXECUTE ON SCHEMA::[ventas] TO [db_rol_kiosco];
DENY EXECUTE ON SCHEMA::[produccion] TO [db_rol_kiosco];
DENY EXECUTE ON SCHEMA::[contabilidad] TO [db_rol_kiosco];
DENY EXECUTE ON SCHEMA::[fiscal] TO [db_rol_kiosco];
DENY EXECUTE ON SCHEMA::[crm] TO [db_rol_kiosco];
DENY EXECUTE ON SCHEMA::[catalogo] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarErrorBD] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarAuditoria] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerUsuarioPorID] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_AutenticarUsuario] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerValorConfiguracion] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarIntentoLogin] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoCuenta] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerDescriptoresFacialesKiosco] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_RegistrarMarcajeKiosco] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerResumenAsistencia] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerTurnoLaboralActivoDefecto] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ActualizarSalidaAsistenciaKiosco] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_ActualizarEntradaAsistenciaKiosco] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[rrhh].[sp_InsertarEntradaAsistenciaKiosco] TO [db_rol_kiosco];
DENY EXECUTE ON OBJECT::[rrhh].[sp_ListarNominasPeriodo] TO [db_rol_kiosco];
DENY EXECUTE ON OBJECT::[rrhh].[sp_ListarNominasRecientes] TO [db_rol_kiosco];
GO

-- 9.6 db_rol_portal_cliente: Exclusivamente catálogo público, sus propias cotizaciones y seguimiento de pedido
DENY EXECUTE ON SCHEMA::[rrhh] TO [db_rol_portal_cliente];
DENY EXECUTE ON SCHEMA::[produccion] TO [db_rol_portal_cliente];
DENY EXECUTE ON SCHEMA::[contabilidad] TO [db_rol_portal_cliente];
DENY EXECUTE ON SCHEMA::[fiscal] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_ActualizarEstadoCotizacion] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_CotizarPedidoAdmin] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_ObtenerCotizacionesPendientesAdmin] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_ActualizarCliente] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_ActualizarClienteAdmin] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarUsuariosYRoles] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarBitacoraErrores] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[seguridad].[sp_ListarAuditoria] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarErrorBD] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RegistrarIntentoLogin] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoCuenta] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionGlobal] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionClave] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerValorConfiguracion] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LeerDesafioAuth] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerMaxExpiracionDesafioSMS] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ConsumirDesafiosFamilia] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_InsertarDesafioAuth] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_RevocarDesafioPorToken] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_IncrementarIntentosDesafio] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_MarcarDesafioVerificado] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerCatalogoActivo] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerCategoriasConProductosActivos] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerProductosPOS] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[catalogo].[sp_ObtenerIngredientesPOS] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerClientePorID] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerClientePorTelefono] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_CrearInvitadoTemporal] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_RegistrarClienteVerificado] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ListarCotizacionesCliente] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_CrearCotizacion] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_VincularCotizacionesSesionCliente] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerCotizacionesPorClienteID] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerCotizacionesPorSessionID] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerCotizacionPorIDBloqueo] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_CancelarCotizacionCliente] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_ObtenerCotizacionParaAceptarBloqueo] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_VincularCotizacionPorID] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_AceptarCotizacionCliente] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_ConsultarSeguimientoPedido] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoEncargoPublico] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoAdelantoPublico] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_SeguimientoProductosPublico] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_VerificarColumnaEstadoFiscalFacturas] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerTurnoAbierto] TO [db_rol_portal_cliente];
GO

-- ============================================================================
-- Procedimiento rrhh.sp_CambiarEstadoPerfilPuesto
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_CambiarEstadoPerfilPuesto]
                @Cargo NVARCHAR(100),
                @Activo BIT,
                @ActorID INT = NULL,
                @IP VARCHAR(50) = NULL
            AS
            BEGIN
                SET NOCOUNT ON;
                UPDATE [rrhh].[PerfilesPuesto]
                SET Activo = @Activo,
                    ActualizadoEn = SYSUTCDATETIME(),
                    ActualizadoPor = @ActorID
                WHERE Cargo = @Cargo;

                IF @@ROWCOUNT = 0
                BEGIN
                    THROW 51053, 'El cargo especificado no existe.', 1;
                END

                IF @ActorID IS NOT NULL
                BEGIN
                    EXEC [seguridad].[sp_RegistrarAuditoria] @ActorID, 'PERFIL_ESTADO', 'PerfilPuesto', NULL,
                         NULL, @Cargo, @IP;
                END
            END
GO

-- ============================================================================
-- Procedimiento rrhh.sp_ListarEscalaSalarial
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_ListarEscalaSalarial]
        AS
        BEGIN
            SET NOCOUNT ON;
            SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            ORDER BY id ASC;
        END
GO

-- ============================================================================
-- Procedimiento rrhh.sp_ObtenerEscalaSalarialPorCargo
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_ObtenerEscalaSalarialPorCargo]
            @Cargo NVARCHAR(100)
        AS
        BEGIN
            SET NOCOUNT ON;
            DECLARE @CargoClean NVARCHAR(100) = LTRIM(RTRIM(@Cargo));

            -- 1. Coincidencia exacta
            IF EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) = LOWER(@CargoClean))
            BEGIN
                SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) = LOWER(@CargoClean);
                RETURN;
            END

            -- 2. Mapeos o prefijo
            IF LOWER(@CargoClean) = 'cajero' OR LOWER(@CargoClean) LIKE 'cajero%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cajero', 'cajero/depedienta');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'cocina' OR LOWER(@CargoClean) LIKE 'coci%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cocina', 'cocinero');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'gerente' OR LOWER(@CargoClean) LIKE 'gerente%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('gerente', 'gerente general');
                RETURN;
            END

            -- 3. LIKE genérico
            SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            WHERE LOWER(cargo) LIKE '%' + LOWER(@CargoClean) + '%'
               OR LOWER(@CargoClean) LIKE '%' + LOWER(cargo) + '%'
            ORDER BY id ASC;
        END
GO


-- ============================================================================
-- Procedimientos Almacenados Outbox / Alertas SMTP
-- ============================================================================
CREATE OR ALTER PROCEDURE seguridad.sp_EncolarAlertaSMTP
    @ErrorID BIGINT,
    @DestinatariosJSON NVARCHAR(MAX)=NULL,
    @Forzar BIT=0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @LockResult INT;
        EXEC @LockResult=sys.sp_getapplock @Resource=N'panaderia.smtp.outbox.v1',
             @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;
        INSERT INTO seguridad.AlertasSMTPOutbox(ErrorID, DedupKey, DestinatariosJSON, Forzar)
        SELECT b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError,120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)), @DestinatariosJSON, @Forzar
        FROM seguridad.BitacoraErrores b
        WHERE b.ID=@ErrorID AND b.NotificadoSMTP=0
          AND NOT EXISTS(SELECT 1 FROM seguridad.AlertasSMTPOutbox o WHERE o.ErrorID=b.ID);
        COMMIT;
        SELECT CAST(CASE WHEN EXISTS(SELECT 1 FROM seguridad.AlertasSMTPOutbox WHERE ErrorID=@ErrorID)
                        THEN 1 ELSE 0 END AS BIT) AS Encolada;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK;
        THROW;
    END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE seguridad.sp_ReclamarAlertaSMTP
    @ErrorID BIGINT=NULL,
    @VentanaSegundos INT=300,
    @LeaseSegundos INT=300,
    @SembrarLote INT=20
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @SembrarLote NOT BETWEEN 0 AND 100 OR @VentanaSegundos NOT BETWEEN 0 AND 86400
       OR @LeaseSegundos NOT BETWEEN 60 AND 3600
        THROW 51071, 'Limites SMTP invalidos.', 1;
    DECLARE @Ahora DATETIME2(3)=SYSUTCDATETIME(), @Elegido BIGINT, @Clave BINARY(32),
            @Token UNIQUEIDENTIFIER=NEWID(), @LockResult INT;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC @LockResult=sys.sp_getapplock @Resource=N'panaderia.smtp.outbox.v1',
             @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;

        -- Recover SQL-only errors and events persisted before enqueue failure.
        INSERT INTO seguridad.AlertasSMTPOutbox(ErrorID, DedupKey)
        SELECT TOP (@SembrarLote) b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError,120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER))
        FROM seguridad.BitacoraErrores b
        WHERE b.NotificadoSMTP=0
          AND NOT EXISTS(SELECT 1 FROM seguridad.AlertasSMTPOutbox o WHERE o.ErrorID=b.ID)
        ORDER BY b.ID;

        -- Keep duplicate log records immutable and show suppression in outbox.
        UPDATE TOP (100) o SET Estado='Suppressed', ClaimToken=NULL, LeaseHasta=NULL
        FROM seguridad.AlertasSMTPOutbox o
        JOIN seguridad.AlertasSMTPDedup d ON d.DedupKey=o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.Forzar=0
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta<=@Ahora)
          AND d.UltimoEnvio>DATEADD(SECOND,-@VentanaSegundos,@Ahora)
          AND (@ErrorID IS NULL OR o.ErrorID=@ErrorID);

        SELECT TOP(1) @Elegido=o.ErrorID, @Clave=o.DedupKey
        FROM seguridad.AlertasSMTPOutbox o
        LEFT JOIN seguridad.AlertasSMTPDedup d ON d.DedupKey=o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.DisponibleDesde<=@Ahora
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta<=@Ahora)
          AND (d.LeaseHasta IS NULL OR d.LeaseHasta<=@Ahora)
          AND (o.Forzar=1 OR d.UltimoEnvio IS NULL OR d.UltimoEnvio<=DATEADD(SECOND,-@VentanaSegundos,@Ahora))
          AND (@ErrorID IS NULL OR o.ErrorID=@ErrorID)
        ORDER BY o.DisponibleDesde, o.ErrorID;

        IF @Elegido IS NOT NULL
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM seguridad.AlertasSMTPDedup WHERE DedupKey=@Clave)
                INSERT INTO seguridad.AlertasSMTPDedup(DedupKey) VALUES(@Clave);
            UPDATE seguridad.AlertasSMTPDedup
               SET ClaimToken=@Token, LeaseHasta=DATEADD(SECOND,@LeaseSegundos,@Ahora)
             WHERE DedupKey=@Clave;
            UPDATE seguridad.AlertasSMTPOutbox SET Estado='Sending', ClaimToken=@Token,
                   LeaseHasta=DATEADD(SECOND,@LeaseSegundos,@Ahora), Intentos=Intentos+1
             WHERE ErrorID=@Elegido;
        END;
        COMMIT;
        SELECT b.*, o.ClaimToken, o.DestinatariosJSON
        FROM seguridad.AlertasSMTPOutbox o
        JOIN seguridad.BitacoraErrores b ON b.ID=o.ErrorID
        WHERE o.ErrorID=@Elegido AND o.ClaimToken=@Token;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK;
        THROW;
    END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE seguridad.sp_FinalizarAlertaSMTP
    @ErrorID BIGINT,
    @Token UNIQUEIDENTIFIER,
    @Enviado BIT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @Clave BINARY(32), @Ahora DATETIME2(3)=SYSUTCDATETIME(), @LockResult INT,
            @Finalizada BIT=0;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC @LockResult=sys.sp_getapplock @Resource=N'panaderia.smtp.outbox.v1',
             @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;
        SELECT @Clave=o.DedupKey FROM seguridad.AlertasSMTPOutbox o
        JOIN seguridad.AlertasSMTPDedup d ON d.DedupKey=o.DedupKey
        WHERE o.ErrorID=@ErrorID AND o.ClaimToken=@Token AND d.ClaimToken=@Token
          AND o.Estado='Sending';
        -- Stale workers cannot ACK, release, or mark a newer worker's claim.
        IF @Clave IS NOT NULL
        BEGIN
            UPDATE seguridad.AlertasSMTPOutbox SET Estado=CASE WHEN @Enviado=1 THEN 'Sent' ELSE 'Pending' END,
                ClaimToken=NULL, LeaseHasta=NULL,
                DisponibleDesde=DATEADD(SECOND, CASE WHEN Intentos>=6 THEN 300 ELSE 10*Intentos END, @Ahora)
            WHERE ErrorID=@ErrorID;
            UPDATE seguridad.AlertasSMTPDedup SET ClaimToken=NULL, LeaseHasta=NULL,
                UltimoEnvio=CASE WHEN @Enviado=1 THEN @Ahora ELSE UltimoEnvio END
            WHERE DedupKey=@Clave AND ClaimToken=@Token;
            IF @Enviado=1
                EXEC seguridad.sp_MarcarErrorNotificadoSMTP @ErrorID=@ErrorID;
            SET @Finalizada=1;
        END;
        COMMIT;
        SELECT @Finalizada AS Finalizada;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK;
        THROW;
    END CATCH;
END;
GO
GRANT EXECUTE ON OBJECT::seguridad.sp_EncolarAlertaSMTP TO db_rol_alertas_worker;
GRANT EXECUTE ON OBJECT::seguridad.sp_ReclamarAlertaSMTP TO db_rol_alertas_worker;
GRANT EXECUTE ON OBJECT::seguridad.sp_FinalizarAlertaSMTP TO db_rol_alertas_worker;
GO


-- ============================================================================
-- Procedimientos Almacenados de Recursos Humanos (Perfiles de Puesto y Escala)
-- ============================================================================
-- ============================================================================
-- Procedimiento rrhh.sp_CambiarEstadoPerfilPuesto
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_CambiarEstadoPerfilPuesto]
                @Cargo NVARCHAR(100),
                @Activo BIT,
                @ActorID INT = NULL,
                @IP VARCHAR(50) = NULL
            AS
            BEGIN
                SET NOCOUNT ON;
                UPDATE [rrhh].[PerfilesPuesto]
                SET Activo = @Activo,
                    ActualizadoEn = SYSUTCDATETIME(),
                    ActualizadoPor = @ActorID
                WHERE Cargo = @Cargo;

                IF @@ROWCOUNT = 0
                BEGIN
                    THROW 51053, 'El cargo especificado no existe.', 1;
                END

                IF @ActorID IS NOT NULL
                BEGIN
                    EXEC [seguridad].[sp_RegistrarAuditoria] @ActorID, 'PERFIL_ESTADO', 'PerfilPuesto', NULL,
                         NULL, @Cargo, @IP;
                END
            END
GO

-- ============================================================================
-- Procedimiento rrhh.sp_ListarEscalaSalarial
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_ListarEscalaSalarial]
        AS
        BEGIN
            SET NOCOUNT ON;
            SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            ORDER BY id ASC;
        END
GO

-- ============================================================================
-- Procedimiento rrhh.sp_ObtenerEscalaSalarialPorCargo
-- ============================================================================
CREATE OR ALTER CREATE   PROCEDURE [rrhh].[sp_ObtenerEscalaSalarialPorCargo]
            @Cargo NVARCHAR(100)
        AS
        BEGIN
            SET NOCOUNT ON;
            DECLARE @CargoClean NVARCHAR(100) = LTRIM(RTRIM(@Cargo));

            -- 1. Coincidencia exacta
            IF EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) = LOWER(@CargoClean))
            BEGIN
                SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) = LOWER(@CargoClean);
                RETURN;
            END

            -- 2. Mapeos o prefijo
            IF LOWER(@CargoClean) = 'cajero' OR LOWER(@CargoClean) LIKE 'cajero%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cajero', 'cajero/depedienta');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'cocina' OR LOWER(@CargoClean) LIKE 'coci%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cocina', 'cocinero');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'gerente' OR LOWER(@CargoClean) LIKE 'gerente%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('gerente', 'gerente general');
                RETURN;
            END

            -- 3. LIKE genérico
            SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            WHERE LOWER(cargo) LIKE '%' + LOWER(@CargoClean) + '%'
               OR LOWER(@CargoClean) LIKE '%' + LOWER(cargo) + '%'
            ORDER BY id ASC;
        END
GO


-- ============================================================================
-- 10. DATOS SEMILLA BASE DE PRODUCCIÓN (CONFIGURACIÓN, CATÁLOGOS Y NIIF)
-- ============================================================================
-- ============================================================================
-- Semilla para [seguridad].[Roles] (6 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [seguridad].[Roles])
BEGIN
    SET IDENTITY_INSERT [seguridad].[Roles] ON;
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (1, N'SuperAdmin', N'Administrador General y Auditoría Técnica (db_rol_superadmin): Control total de 8 esquemas, auditoría forense y bitácora SMTP');
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (2, N'Admin', N'Gerencia y Administración (db_rol_gerencia): Dashboard, Contabilidad, Planilla/RRHH, Fiscal DGI, Arqueos y Usuarios');
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (3, N'Estandar', N'Cajero POS y Atención (db_rol_cajero_pos): Punto de Venta, Turnos, Facturación, Cotizaciones, Monitor y Arqueo Etapa 1');
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (4, N'Invitado', N'Portal Cliente / Consulta (db_rol_portal_cliente): Catálogo público, solicitud de cotizaciones propias y seguimiento');
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (5, N'Operativo', N'Producción, Cocina y Bodega (db_rol_produccion): Monitor KDS, Producción, Recetas, Inventario de Materia Prima y Mermas');
    INSERT INTO [seguridad].[Roles] ([ID], [Nombre], [Descripcion]) VALUES (6, N'Kiosco', N'Terminal Biométrica de Asistencia (db_rol_kiosco): Kiosco de reconocimiento facial SFace y marcaje de entrada/salida');
    SET IDENTITY_INSERT [seguridad].[Roles] OFF;
END
GO

-- ============================================================================
-- Semilla para [crm].[NivelesConfianza] (3 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [crm].[NivelesConfianza])
BEGIN
    SET IDENTITY_INSERT [crm].[NivelesConfianza] ON;
    INSERT INTO [crm].[NivelesConfianza] ([ID], [Nombre], [ComprasMinimas]) VALUES (1, N'Nuevo', 0);
    INSERT INTO [crm].[NivelesConfianza] ([ID], [Nombre], [ComprasMinimas]) VALUES (2, N'Frecuente', 3);
    INSERT INTO [crm].[NivelesConfianza] ([ID], [Nombre], [ComprasMinimas]) VALUES (3, N'VIP', 10);
    SET IDENTITY_INSERT [crm].[NivelesConfianza] OFF;
END
GO

-- ============================================================================
-- Semilla para [catalogo].[Categorias] (16 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [catalogo].[Categorias])
BEGIN
    SET IDENTITY_INSERT [catalogo].[Categorias] ON;
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (1, N'Pan Salado', N'Bolillos, pan pizza, baguettes');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (2, N'Pan Dulce', N'Conchas, donas, panuelitos');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (3, N'Reposteria', N'Pasteles y queques para encargo');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (4, N'Bebidas', N'Cafe, gaseosas, jugos');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (5, N'Postres Frios', N'Tres leches, selva negra, gelatinas');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (6, N'Galletas', N'Galletas de jamon, mantequilla');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (7, N'Harinas', N'Categoría Harinas');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (8, N'Lácteos', N'Categoría Lácteos');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (9, N'Grasas', N'Categoría Grasas');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (10, N'Azúcares', N'Categoría Azúcares');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (11, N'Levaduras/Químicos', N'Categoría Levaduras/Químicos');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (12, N'Saborizantes', N'Categoría Saborizantes');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (13, N'Rellenos/Otros', N'Categoría Rellenos/Otros');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (14, N'Empaques', N'Categoría Empaques');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (15, N'Panadería', N'Categoría Panadería');
    INSERT INTO [catalogo].[Categorias] ([ID], [Nombre], [Descripcion]) VALUES (16, N'Repostería', N'Categoría Repostería');
    SET IDENTITY_INSERT [catalogo].[Categorias] OFF;
END
GO

-- ============================================================================
-- Semilla para [catalogo].[UnidadesMedida] (6 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [catalogo].[UnidadesMedida])
BEGIN
    SET IDENTITY_INSERT [catalogo].[UnidadesMedida] ON;
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (1, N'Kilogramo', N'Kg');
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (2, N'Litro', N'Lt');
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (3, N'Unidad', N'Ud');
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (4, N'Libra', N'Lb');
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (5, N'Gramo', N'g');
    INSERT INTO [catalogo].[UnidadesMedida] ([ID], [Nombre], [Abreviatura]) VALUES (6, N'Mililitros', N'ml');
    SET IDENTITY_INSERT [catalogo].[UnidadesMedida] OFF;
END
GO

-- ============================================================================
-- Semilla para [seguridad].[ConfiguracionSistema] (27 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [seguridad].[ConfiguracionSistema])
BEGIN
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'dgi_obligaciones', N'', N'Preparación interna DGI; no valida inscripción ni normativa');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'dgi_responsable', N'', N'Preparación interna DGI; no valida inscripción ni normativa');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'dgi_vigente_desde', N'', N'Preparación interna DGI; no valida inscripción ni normativa');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'dgi_vigente_hasta', N'', N'Preparación interna DGI; no valida inscripción ni normativa');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'direccion_negocio', N'', N'Dirección física del negocio');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_autorizacion', N'', N'Referencia de autorización real DGI; no constituye validación automática');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_correo', N'', N'Correo del emisor');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_direccion', N'', N'Dirección del establecimiento');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_razon_social', N'', N'Razón social del emisor');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_regimen', N'Pendiente', N'Pendiente, Cuota fija o General; confirmar con la inscripción DGI');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_ruc', N'', N'RUC del emisor según inscripción');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_serie', N'FAC', N'Serie fija para esta instalación; no editar con ventas existentes');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_sucursal', N'Casa matriz', N'Establecimiento emisor; esta instalación usa una sola serie');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'fiscal_telefono', N'', N'Teléfono del emisor');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'iva_porcentaje', N'0', N'Porcentaje de IVA aplicado');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'max_items_factura', N'50', N'Máximo de líneas por factura');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'moneda_simbolo', N'C$', N'Símbolo de moneda');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'nombre_negocio', N'Panadería Amada', N'Nombre del negocio');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'permitir_invitados', N'1', N'Permitir acceso como cliente invitado');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'smtp_alertas_activo', N'1', N'Activar notificaciones de errores y alertas críticas por correo SMTP (1=Sí, 0=No)');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'smtp_bloqueo_intentos_max', N'5', N'Número máximo de intentos fallidos de login antes de bloquear cuenta y alertar por SMTP');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'smtp_bloqueo_minutos', N'15', N'Minutos de bloqueo automático tras exceder intentos fallidos de login');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'smtp_nivel_minimo', N'ERROR', N'Nivel mínimo para envío de alertas por correo (WARNING, ERROR, CRITICAL)');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'telefono_negocio', N'', N'Teléfono de contacto');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'tipo_cambio_usd', N'36.62', N'Córdobas por dólar según el tipo de cambio oficial BCN; actualizar cuando corresponda');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'totp_obligatorio', N'0', N'Verificación en dos pasos obligatoria para empleados');
    INSERT INTO [seguridad].[ConfiguracionSistema] ([Clave], [Valor], [Descripcion]) VALUES (N'umbral_discrepancia_cordobas', N'50.00', N'Monto en córdobas a partir del cual una discrepancia en arqueo requiere justificación obligatoria');
END
GO

-- ============================================================================
-- Semilla para [contabilidad].[TiposComprobante] (9 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [contabilidad].[TiposComprobante])
BEGIN
    SET IDENTITY_INSERT [contabilidad].[TiposComprobante] ON;
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (1, N'DI', N'Diario', 0, N'CD', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (2, N'IN', N'Ingreso', 3, N'CI', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (3, N'EG', N'Egreso', 0, N'CE', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (4, N'AJ', N'Ajuste', 0, N'CA', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (5, N'CI', N'Cierre', 0, N'CC', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (6, N'AP', N'Apertura', 0, N'CO', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (7, N'NM', N'Nómina', 14, N'CN', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (8, N'FV', N'Factura de Venta', 122, N'FV', 1);
    INSERT INTO [contabilidad].[TiposComprobante] ([ID], [Codigo], [Nombre], [CorrelativoActual], [Prefijo], [Activo]) VALUES (9, N'FC', N'Factura de Compra', 0, N'FC', 1);
    SET IDENTITY_INSERT [contabilidad].[TiposComprobante] OFF;
END
GO

-- ============================================================================
-- Semilla para [contabilidad].[CatalogoCuentas] (129 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [contabilidad].[CatalogoCuentas])
BEGIN
    SET IDENTITY_INSERT [contabilidad].[CatalogoCuentas] ON;
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (1, N'1.1.01.001', N'Caja General (C$)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 11, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (2, N'1.1.02.001', N'Clientes (CxC Comerciales)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 15, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (3, N'1.1.01.004', N'Bancos Moneda Nacional', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 11, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (4, N'2.1.01.001', N'Proveedores Nacionales (CxP)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 45, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (5, N'2.1.03.001', N'IVA Débito Fiscal (15%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 58, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (6, N'3.1.01.001', N'Aporte de Capital — Amada Calero', N'Capital', N'Capital Contable', N'Acreedora', 1, 4, 71, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (7, N'4.1.01.001', N'Ventas de Pan y Repostería', N'Ingreso', N'Ingresos Operativos', N'Acreedora', 1, 4, 81, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (8, N'5.1.01.001', N'Costo de Materia Prima Consumida', N'Costo', N'Costos Operativos', N'Deudora', 1, 4, 92, 1, NULL, 0);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (9, N'1', N'ACTIVOS', N'Activo', N'Activos', N'Deudora', 1, 1, NULL, 0, N'Clase principal de activos', 100);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (10, N'1.1', N'Activo Circulante', N'Activo', N'Activo Circulante', N'Deudora', 1, 2, 9, 0, N'Activos convertibles en efectivo en menos de 12 meses', 110);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (11, N'1.1.01', N'Efectivo y Equivalentes de Efectivo', N'Activo', N'Activo Circulante', N'Deudora', 1, 3, 10, 0, N'Dinero disponible inmediatamente', 111);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (12, N'1.1.01.002', N'Caja General (USD)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 11, 1, N'Efectivo en dólares americanos en caja', 112);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (13, N'1.1.01.003', N'Caja Chica', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 11, 1, N'Fondo fijo para gastos menores', 113);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (14, N'1.1.01.005', N'Bancos Moneda Extranjera', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 11, 1, N'Cuentas bancarias en USD', 115);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (15, N'1.1.02', N'Cuentas y Documentos por Cobrar', N'Activo', N'Activo Circulante', N'Deudora', 1, 3, 10, 0, N'Derechos de cobro a terceros', 121);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (16, N'1.1.02.002', N'Encargos por Cobrar (Saldo Restante)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 15, 1, N'Saldo pendiente de cobro en pasteles por encargo', 122);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (17, N'1.1.02.003', N'Anticipos a Empleados (Vales)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 15, 1, N'Vales y anticipos de sueldo a descontar en nómina', 123);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (18, N'1.1.02.004', N'Anticipos a Proveedores', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 15, 1, N'Pagos anticipados a proveedores de materia prima', 124);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (19, N'1.1.02.005', N'Estimación para Cuentas Incobrables', N'Activo', N'Activo Circulante', N'Acreedora', 1, 4, 15, 1, N'Provisión NIIF para incobrables (contraactivo)', 125);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (20, N'1.1.03', N'Inventarios', N'Activo', N'Activo Circulante', N'Deudora', 1, 3, 10, 0, N'Bienes para la producción y venta', 131);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (21, N'1.1.03.001', N'Inventario de Materia Prima', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 20, 1, N'Harina, azúcar, huevos, manteca, etc.', 132);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (22, N'1.1.03.002', N'Inventario de Productos en Proceso', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 20, 1, N'Pan y pasteles en proceso de elaboración', 133);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (23, N'1.1.03.003', N'Inventario de Productos Terminados', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 20, 1, N'Pan y repostería listo para venta', 134);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (24, N'1.1.03.004', N'Inventario de Suministros y Empaques', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 20, 1, N'Bolsas, cajas, papel, etc.', 135);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (25, N'1.1.04', N'Impuestos Pagados por Anticipado', N'Activo', N'Activo Circulante', N'Deudora', 1, 3, 10, 0, N'Créditos fiscales a favor', 141);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (26, N'1.1.04.001', N'IVA Crédito Fiscal (15%)', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 25, 1, N'IVA pagado en compras, acreditable contra IVA por pagar', 142);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (27, N'1.1.04.002', N'IR Pagado por Anticipado', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 25, 1, N'Pagos a cuenta del IR anual', 143);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (28, N'1.1.04.003', N'Retenciones en la Fuente a Favor', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 25, 1, N'Retenciones hechas al negocio por clientes grandes', 144);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (29, N'1.1.05', N'Gastos Pagados por Anticipado', N'Activo', N'Activo Circulante', N'Deudora', 1, 3, 10, 0, N'Pagos por servicios aún no devengados', 151);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (30, N'1.1.05.001', N'Seguros Pagados por Anticipado', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 29, 1, N'Pólizas de seguro pagadas por adelantado', 152);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (31, N'1.1.05.002', N'Alquileres Pagados por Anticipado', N'Activo', N'Activo Circulante', N'Deudora', 1, 4, 29, 1, N'Renta pagada por adelantado', 153);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (32, N'1.2', N'Activo No Circulante', N'Activo', N'Activo No Circulante', N'Deudora', 1, 2, 9, 0, N'Activos de largo plazo', 160);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (33, N'1.2.01', N'Propiedad, Planta y Equipo', N'Activo', N'Activo No Circulante', N'Deudora', 1, 3, 32, 0, N'Activos fijos tangibles NIIF Sección 17', 161);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (34, N'1.2.01.001', N'Mobiliario y Equipo de Panadería', N'Activo', N'Activo No Circulante', N'Deudora', 1, 4, 33, 1, N'Hornos, amasadoras, vitrinas, mesas de trabajo', 162);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (35, N'1.2.01.002', N'Equipo de Cómputo y POS', N'Activo', N'Activo No Circulante', N'Deudora', 1, 4, 33, 1, N'Computadoras, impresoras térmicas, tablets', 163);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (36, N'1.2.01.003', N'Vehículos de Reparto', N'Activo', N'Activo No Circulante', N'Deudora', 1, 4, 33, 1, N'Vehículos para entregas de pasteles', 164);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (37, N'1.2.01.004', N'Mejoras al Local', N'Activo', N'Activo No Circulante', N'Deudora', 1, 4, 33, 1, N'Remodelaciones y adecuaciones del local', 165);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (38, N'1.2.02', N'Depreciación Acumulada', N'Activo', N'Activo No Circulante', N'Acreedora', 1, 3, 32, 0, N'Desgaste acumulado de activos fijos (contraactivo)', 171);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (39, N'1.2.02.001', N'Dep. Acum. Mobiliario y Equipo', N'Activo', N'Activo No Circulante', N'Acreedora', 1, 4, 38, 1, N'Depreciación acumulada de equipo de panadería', 172);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (40, N'1.2.02.002', N'Dep. Acum. Equipo de Cómputo', N'Activo', N'Activo No Circulante', N'Acreedora', 1, 4, 38, 1, N'Depreciación acumulada de equipo informático', 173);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (41, N'1.2.02.003', N'Dep. Acum. Vehículos', N'Activo', N'Activo No Circulante', N'Acreedora', 1, 4, 38, 1, N'Depreciación acumulada de vehículos', 174);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (42, N'1.2.02.004', N'Dep. Acum. Mejoras al Local', N'Activo', N'Activo No Circulante', N'Acreedora', 1, 4, 38, 1, N'Amortización de mejoras al local', 175);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (43, N'2', N'PASIVOS', N'Pasivo', N'Pasivos', N'Acreedora', 1, 1, NULL, 0, N'Clase principal de pasivos', 200);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (44, N'2.1', N'Pasivo Circulante', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 2, 43, 0, N'Obligaciones a pagar en menos de 12 meses', 210);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (45, N'2.1.01', N'Cuentas y Documentos por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 3, 44, 0, N'Deudas con proveedores y terceros', 211);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (46, N'2.1.01.002', N'Proveedores Extranjeros (CxP)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 45, 1, N'Deudas con proveedores internacionales', 212);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (47, N'2.1.01.003', N'Anticipos Recibidos de Clientes', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 45, 1, N'Adelantos recibidos por encargos de pasteles', 213);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (48, N'2.1.02', N'Obligaciones Laborales', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 3, 44, 0, N'Deudas con empleados e instituciones laborales', 221);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (49, N'2.1.02.001', N'Sueldos y Salarios por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Nómina pendiente de pago', 222);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (50, N'2.1.02.002', N'INSS Laboral por Pagar (7%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Retención INSS laboral por enterar', 223);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (51, N'2.1.02.003', N'INSS Patronal por Pagar (21.5%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Aporte patronal INSS por pagar', 224);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (52, N'2.1.02.004', N'INATEC por Pagar (2%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Aporte INATEC por pagar', 225);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (53, N'2.1.02.005', N'IR Laboral Retenido por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'IR retenido a empleados, pendiente de enterar a DGI', 226);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (54, N'2.1.02.006', N'Vacaciones por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Provisión de vacaciones devengadas Art. 76 Ley 185', 227);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (55, N'2.1.02.007', N'Aguinaldo por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Provisión de décimo tercer mes Art. 93 Ley 185', 228);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (56, N'2.1.02.008', N'Indemnización por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Provisión de indemnización por antigüedad Art. 45 Ley 185', 229);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (57, N'2.1.02.009', N'Pensiones Alimenticias por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 48, 1, N'Retenciones judiciales por pensión alimenticia Ley 870', 230);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (58, N'2.1.03', N'Impuestos por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 3, 44, 0, N'Obligaciones fiscales con DGI y Alcaldía', 231);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (59, N'2.1.03.002', N'IR Anual por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 58, 1, N'Impuesto sobre la renta anual Ley 822', 232);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (60, N'2.1.03.003', N'Anticipo IR Mensual (1%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 58, 1, N'Anticipo mensual sobre ingresos brutos', 233);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (61, N'2.1.03.004', N'Impuesto Municipal por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 58, 1, N'IMI y tributos municipales', 234);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (62, N'2.1.03.005', N'Retenciones en la Fuente por Pagar (2%)', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 58, 1, N'Retenciones IR a proveedores por pagar a DGI', 235);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (63, N'2.1.04', N'Otras Obligaciones a Corto Plazo', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 3, 44, 0, N'Otras deudas a corto plazo', 241);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (64, N'2.1.04.001', N'Préstamos Bancarios a Corto Plazo', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 63, 1, N'Porción corriente de préstamos bancarios', 242);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (65, N'2.1.04.002', N'Intereses por Pagar', N'Pasivo', N'Pasivo Circulante', N'Acreedora', 1, 4, 63, 1, N'Intereses devengados no pagados', 243);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (66, N'2.2', N'Pasivo No Circulante', N'Pasivo', N'Pasivo No Circulante', N'Acreedora', 1, 2, 43, 0, N'Obligaciones a largo plazo', 250);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (67, N'2.2.01', N'Obligaciones a Largo Plazo', N'Pasivo', N'Pasivo No Circulante', N'Acreedora', 1, 3, 66, 0, N'Deudas a más de 12 meses', 251);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (68, N'2.2.01.001', N'Préstamos Bancarios a Largo Plazo', N'Pasivo', N'Pasivo No Circulante', N'Acreedora', 1, 4, 67, 1, N'Financiamiento bancario a largo plazo', 252);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (69, N'3', N'CAPITAL CONTABLE', N'Capital', N'Capital Contable', N'Acreedora', 1, 1, NULL, 0, N'Patrimonio de los propietarios', 300);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (70, N'3.1', N'Capital Contribuido', N'Capital', N'Capital Contable', N'Acreedora', 1, 2, 69, 0, N'Aportes de los propietarios', 310);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (71, N'3.1.01', N'Capital Social', N'Capital', N'Capital Contable', N'Acreedora', 1, 3, 70, 0, N'Capital social del negocio', 311);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (72, N'3.2', N'Capital Ganado', N'Capital', N'Capital Contable', N'Acreedora', 1, 2, 69, 0, N'Resultados acumulados del negocio', 320);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (73, N'3.2.01', N'Resultados', N'Capital', N'Capital Contable', N'Acreedora', 1, 3, 72, 0, N'Utilidades y pérdidas', 321);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (74, N'3.2.01.001', N'Utilidades Retenidas (Acumuladas)', N'Capital', N'Capital Contable', N'Acreedora', 1, 4, 73, 1, N'Ganancias acumuladas de ejercicios anteriores', 322);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (75, N'3.2.01.002', N'Utilidad del Ejercicio', N'Capital', N'Capital Contable', N'Acreedora', 1, 4, 73, 1, N'Resultado positivo del periodo actual', 323);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (76, N'3.2.01.003', N'Pérdida del Ejercicio', N'Capital', N'Capital Contable', N'Deudora', 1, 4, 73, 1, N'Resultado negativo del periodo actual', 324);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (77, N'3.2.02', N'Reservas', N'Capital', N'Capital Contable', N'Acreedora', 1, 3, 72, 0, N'Reservas legales y voluntarias', 331);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (78, N'3.2.02.001', N'Reserva Legal (10%)', N'Capital', N'Capital Contable', N'Acreedora', 1, 4, 77, 1, N'Reserva legal obligatoria sobre utilidades', 332);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (79, N'4', N'INGRESOS', N'Ingreso', N'Ingresos', N'Acreedora', 1, 1, NULL, 0, N'Clase principal de ingresos', 400);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (80, N'4.1', N'Ingresos Operativos', N'Ingreso', N'Ingresos Operativos', N'Acreedora', 1, 2, 79, 0, N'Ingresos del giro principal del negocio', 410);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (81, N'4.1.01', N'Ventas', N'Ingreso', N'Ingresos Operativos', N'Acreedora', 1, 3, 80, 0, N'Ingresos por venta de productos', 411);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (82, N'4.1.01.002', N'Ventas de Pasteles y Encargos', N'Ingreso', N'Ingresos Operativos', N'Acreedora', 1, 4, 81, 1, N'Ventas de pasteles personalizados por encargo', 412);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (83, N'4.1.01.003', N'Ventas de Bebidas', N'Ingreso', N'Ingresos Operativos', N'Acreedora', 1, 4, 81, 1, N'Ventas de café, gaseosas, jugos', 413);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (84, N'4.1.01.004', N'Devoluciones y Descuentos sobre Ventas', N'Ingreso', N'Ingresos Operativos', N'Deudora', 1, 4, 81, 1, N'Contra-ingreso por devoluciones y descuentos', 414);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (85, N'4.2', N'Ingresos No Operativos', N'Ingreso', N'Ingresos No Operativos', N'Acreedora', 1, 2, 79, 0, N'Ingresos fuera del giro normal', 420);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (86, N'4.2.01', N'Otros Ingresos', N'Ingreso', N'Ingresos No Operativos', N'Acreedora', 1, 3, 85, 0, N'Ingresos extraordinarios y financieros', 421);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (87, N'4.2.01.001', N'Ganancia por Diferencial Cambiario', N'Ingreso', N'Ingresos No Operativos', N'Acreedora', 1, 4, 86, 1, N'Ganancia por fluctuación USD/NIO', 422);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (88, N'4.2.01.002', N'Ingresos Financieros (Intereses)', N'Ingreso', N'Ingresos No Operativos', N'Acreedora', 1, 4, 86, 1, N'Intereses ganados en cuentas bancarias', 423);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (89, N'4.2.01.003', N'Otros Ingresos No Operativos', N'Ingreso', N'Ingresos No Operativos', N'Acreedora', 1, 4, 86, 1, N'Ingresos varios no recurrentes', 424);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (90, N'5', N'COSTOS', N'Costo', N'Costos', N'Deudora', 1, 1, NULL, 0, N'Clase principal de costos', 500);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (91, N'5.1', N'Costo de Ventas', N'Costo', N'Costo de Ventas', N'Deudora', 1, 2, 90, 0, N'Costo de los bienes vendidos', 510);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (92, N'5.1.01', N'Costos Directos de Producción', N'Costo', N'Costo de Ventas', N'Deudora', 1, 3, 91, 0, N'Costos directos de la producción panadera', 511);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (93, N'5.1.01.002', N'Mano de Obra Directa (Panaderos)', N'Costo', N'Costo de Ventas', N'Deudora', 1, 4, 92, 1, N'Salario de panaderos asignado a producción', 512);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (94, N'5.1.01.003', N'Costos Indirectos de Fabricación (CIF)', N'Costo', N'Costo de Ventas', N'Deudora', 1, 4, 92, 1, N'Gas, energía, mantenimiento de equipo de producción', 513);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (95, N'5.1.02', N'Pérdidas Operativas', N'Costo', N'Costo de Ventas', N'Deudora', 1, 3, 91, 0, N'Pérdidas inherentes a la operación', 521);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (96, N'5.1.02.001', N'Mermas y Desperdicios (Pan Frío)', N'Costo', N'Costo de Ventas', N'Deudora', 1, 4, 95, 1, N'Pan frío, defectuoso, vencido — Tabla Mermas del sistema', 522);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (97, N'6', N'GASTOS DE OPERACIÓN', N'Gasto', N'Gastos', N'Deudora', 1, 1, NULL, 0, N'Clase principal de gastos operativos', 600);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (98, N'6.1', N'Gastos de Administración', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 2, 97, 0, N'Gastos del área administrativa', 610);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (99, N'6.1.01', N'Gastos de Personal Administrativo', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 3, 98, 0, N'Costos de personal administrativo', 611);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (100, N'6.1.01.001', N'Sueldos y Salarios (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Sueldos del personal administrativo y gerencial', 612);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (101, N'6.1.01.002', N'INSS Patronal (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Aporte patronal INSS del personal administrativo', 613);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (102, N'6.1.01.003', N'INATEC (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Aporte INATEC del personal administrativo', 614);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (103, N'6.1.01.004', N'Aguinaldo (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Provisión de aguinaldo del personal administrativo', 615);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (104, N'6.1.01.005', N'Vacaciones (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Provisión de vacaciones del personal administrativo', 616);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (105, N'6.1.01.006', N'Indemnización (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 99, 1, N'Provisión de indemnización del personal administrativo', 617);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (106, N'6.1.02', N'Gastos Generales de Administración', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 3, 98, 0, N'Gastos generales del negocio', 621);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (107, N'6.1.02.001', N'Alquiler del Local', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Renta mensual del local comercial', 622);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (108, N'6.1.02.002', N'Servicios Públicos (Agua, Luz, Internet)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Servicios básicos del negocio', 623);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (109, N'6.1.02.003', N'Útiles y Papelería de Oficina', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Material de oficina y papelería', 624);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (110, N'6.1.02.004', N'Depreciación de Equipo (Admin)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Gasto por depreciación de activos administrativos', 625);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (111, N'6.1.02.005', N'Mantenimiento y Reparaciones', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Mantenimiento de equipo, local e instalaciones', 626);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (112, N'6.1.02.006', N'Seguros', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Pólizas de seguro del negocio', 627);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (113, N'6.1.02.007', N'Servicios Profesionales (Contables/Legal)', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Honorarios de contador, abogado, etc.', 628);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (114, N'6.1.02.008', N'Gastos Varios de Administración', N'Gasto', N'Gastos de Administración', N'Deudora', 1, 4, 106, 1, N'Egresos privados no clasificados del sistema', 629);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (115, N'6.2', N'Gastos de Venta', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 2, 97, 0, N'Gastos relacionados con la actividad comercial', 640);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (116, N'6.2.01', N'Gastos de Personal de Ventas', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 3, 115, 0, N'Costos de personal de ventas (dependientas)', 641);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (117, N'6.2.01.001', N'Sueldos y Salarios (Ventas)', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 116, 1, N'Sueldos de dependientas del POS', 642);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (118, N'6.2.01.002', N'INSS Patronal (Ventas)', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 116, 1, N'Aporte patronal INSS del personal de ventas', 643);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (119, N'6.2.01.003', N'INATEC (Ventas)', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 116, 1, N'Aporte INATEC del personal de ventas', 644);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (120, N'6.2.02', N'Gastos Generales de Venta', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 3, 115, 0, N'Gastos generales del área comercial', 651);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (121, N'6.2.02.001', N'Empaques y Material de Empaque', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 120, 1, N'Bolsas, cajas para pasteles, envolturas', 652);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (122, N'6.2.02.002', N'Publicidad y Promoción', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 120, 1, N'Publicidad, redes sociales, promociones', 653);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (123, N'6.2.02.003', N'Transporte y Entregas', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 120, 1, N'Combustible y costos de entrega de encargos', 654);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (124, N'6.2.02.004', N'Depreciación de Equipo (Ventas)', N'Gasto', N'Gastos de Venta', N'Deudora', 1, 4, 120, 1, N'Gasto por depreciación de equipo del área de ventas', 655);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (125, N'6.3', N'Gastos Financieros', N'Gasto', N'Gastos Financieros', N'Deudora', 1, 2, 97, 0, N'Costos del financiamiento', 660);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (126, N'6.3.01', N'Costos Financieros', N'Gasto', N'Gastos Financieros', N'Deudora', 1, 3, 125, 0, N'Gastos bancarios y financieros', 661);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (127, N'6.3.01.001', N'Intereses sobre Préstamos', N'Gasto', N'Gastos Financieros', N'Deudora', 1, 4, 126, 1, N'Intereses de préstamos bancarios', 662);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (128, N'6.3.01.002', N'Comisiones Bancarias', N'Gasto', N'Gastos Financieros', N'Deudora', 1, 4, 126, 1, N'Comisiones y mantenimiento de cuentas bancarias', 663);
    INSERT INTO [contabilidad].[CatalogoCuentas] ([ID], [Codigo], [Nombre], [Clase], [Grupo], [Naturaleza], [Activa], [Nivel], [CuentaPadreID], [EsTransaccional], [Descripcion], [OrdenVisualizacion]) VALUES (129, N'6.3.01.003', N'Pérdida por Diferencial Cambiario', N'Gasto', N'Gastos Financieros', N'Deudora', 1, 4, 126, 1, N'Pérdida por fluctuación USD/NIO', 664);
    SET IDENTITY_INSERT [contabilidad].[CatalogoCuentas] OFF;
END
GO

-- ============================================================================
-- Semilla para [rrhh].[escala_salarial] (15 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [rrhh].[escala_salarial])
BEGIN
    SET IDENTITY_INSERT [rrhh].[escala_salarial] ON;
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (1, N'I', N'Limpieza', NULL, 100, 6519.58);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (2, N'II', N'Panadero Aprendiz', 101, 126, 8572.96);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (3, N'III', N'Cajero/Depedienta', 127, 159, 10626.34);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (4, N'III', N'Cajero', 127, 159, 10626.34);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (5, N'IV', N'Cocinero', 160, 200, 12679.72);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (6, N'IV', N'Cocina', 160, 200, 12679.72);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (7, N'V', N'Panadero Junior', 201, 252, 14733.10);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (8, N'VI', N'Jefe de Inventario', 253, 317, 16786.48);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (9, N'VII', N'Panadero Senior', 318, 400, 18839.86);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (10, N'VIII', N'Contador', 401, 504, 20893.24);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (11, N'IX', N'Maestro Panadero', 505, 635, 22946.62);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (12, N'X', N'Gerente General', 636, 800, 25000.00);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (13, N'X', N'Gerente', 636, 800, 25000.00);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (14, N'VIII', N'Ingeniero electronico', 401, 504, 20893.24);
    INSERT INTO [rrhh].[escala_salarial] ([id], [nivel], [cargo], [limite_inferior], [limite_superior], [salario_base]) VALUES (15, N'II', N'Panadero', 101, 126, 8572.96);
    SET IDENTITY_INSERT [rrhh].[escala_salarial] OFF;
END
GO

-- ============================================================================
-- Semilla para [rrhh].[PerfilesPuesto] (12 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [rrhh].[PerfilesPuesto])
BEGIN
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Cajero', N'Atender al cliente con amabilidad y eficiencia en el mostrador, despachar los productos de panadería y repostería, y procesar los cobros a través del sistema POS, garantizando un cuadre de caja exacto y una excelente experiencia de compra.', N'1. Recibir y saludar a los clientes, ofrecer sugerencias de productos y empaquetar adecuadamente los panes, postres y bebidas solicitados.
2. Registrar con precisión todas las ventas en el sistema informático (POS) y procesar pagos en efectivo, transferencias o tarjetas de crédito/débito.
3. Realizar el arqueo de caja (apertura y cierre de turno) entregando el reporte y los valores correspondientes a la Gerencia.
4. Mantener surtidas, ordenadas y limpias las vitrinas de exhibición, verificando precios visibles y retirando producto mermado.', N'• Habilidad: Bachiller o estudiante universitario (Administración, Contabilidad). Manejo fluido de computadoras, sistemas POS y datáfonos. Experiencia de 0 a 1 año en atención y caja. Excelente comunicación y agilidad en cobros.
• Esfuerzo: Físico moderado (de pie detrás del mostrador). Esfuerzo mental regular a alto en cobros, cálculo de cambio y cuadre de caja.
• Responsabilidad: Custodia y cuidado de terminales POS y valores en efectivo; emisión correcta de facturas y rotación PEPS en vitrinas con pinzas y guantes.', N'2026-10-25 03:58:30.085067', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Cocina', N'Preparar, sazonar y cocinar los alimentos complementarios a la panadería (rellenos para repostería, bocadillos salados, o menús si el local ofrece servicio de comedor), garantizando un excelente sabor, textura y estricta inocuidad alimentaria.', N'1. Preparar y cocinar rellenos dulces y salados (crema pastelera, jaleas, carnes, pollos, quesos) necesarios para los productos horneados.
2. Picar, porcionar y almacenar correctamente verduras, carnes y embutidos, aplicando la técnica PEPS (Primeras Entradas, Primeras Salidas).
3. Elaborar platillos o bocadillos del menú diario según la demanda de la vitrina, manteniendo siempre el mismo estándar de sabor.
4. Lavar, desinfectar y organizar todos los utensilios de cocina (ollas, sartenes, cuchillos) y mantener la estufa y campana extractora limpias.', N'• Habilidad: Bachiller. Técnico en Cocina Profesional o Gastronomía Básica con carnet de manipulación de alimentos MINSA. Experiencia de 1 a 2 años en cocina o comedores. Excelente paladar, rapidez e improvisación culinaria.
• Esfuerzo: Físico moderado a intenso (picado y mezcla continua en ollas grandes, de pie). Mental alto en horas pico vigilando fuegos y recetas.
• Responsabilidad: Cuidado estricto de cuchillos y estufas industriales; prevención de contaminación cruzada en perecederos; seguridad contra fugas de gas y derrames de aceite hirviendo.', N'2026-10-25 04:27:55.588590', 1, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Contador', N'Registrar, analizar y controlar las operaciones contables, fiscales y financieras de Brajher''s Cake, asegurando la presentación oportuna de estados financieros y el cumplimiento estricto de las obligaciones tributarias y laborales ante las autoridades correspondientes.', N'1. Registrar diariamente los ingresos, egresos, facturas de compras y ventas en el sistema contable de la panadería.
2. Elaborar y presentar las declaraciones de impuestos mensuales y anuales ante la DGI y la Alcaldía (Anticipo IR, IVA, IMI, etc.).
3. Realizar las conciliaciones bancarias, liquidación de la nómina (pago a empleados) y declaración de planillas ante el INSS y MITRAB.
4. Emitir estados financieros (Balance General y Estado de Resultados) y brindar asesoría financiera a la Gerencia para la toma de decisiones.', N'• Habilidad: Licenciado en Contaduría Pública y Finanzas (deseable CPA). Dominio de leyes tributarias nicaragüenses, laborales y software contable. Experiencia de 3 a 5 años como contador general en pymes. Rigor analítico y control interno.
• Esfuerzo: Físico sedentario/mínimo de oficina. Mental muy intenso en concentración analítica de grandes volúmenes de datos numéricos y cuadres al centavo.
• Responsabilidad: Integridad y confidencialidad absoluta de libros contables, firmas electrónicas y tokens bancarios; prevención de multas fiscales; auditoría de soportes.', N'2026-10-25 03:58:30.838025', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Gerente', N'Planificar, organizar, dirigir y controlar todos los recursos humanos, materiales y financieros de Brajher''s Cake, definiendo el rumbo estratégico del negocio para garantizar su rentabilidad, crecimiento sostenible y posicionamiento en el mercado local.', N'1. Tomar las decisiones estratégicas de negocio: fijación de precios, alianzas con grandes proveedores, planes de expansión y estrategias de marketing.
2. Administrar el flujo de efectivo, autorizar los pagos de nómina, gastos operativos e inversiones en maquinaria nueva.
3. Contratar, evaluar y gestionar el desarrollo del personal, estableciendo las políticas internas y asegurando un buen clima laboral.
4. Supervisar indirectamente todas las áreas (producción, inventario, ventas y finanzas) mediante la revisión de reportes e indicadores de desempeño (KPIs).', N'• Habilidad: Licenciatura en Administración de Empresas, Ingeniería Industrial, Economía o afines (deseable especialización en Pymes o Finanzas). Más de 5 años de experiencia liderando negocios de alimentos. Visión de negocio, negociación y liderazgo inspirador.
• Esfuerzo: Físico ligero (oficina, planta y gestiones externas). Mental máximo como responsable última del éxito comercial, rentabilidad y solución de crisis mayores.
• Responsabilidad: Protección patrimonial de infraestructura y activos, cumplimiento legal patronal ante el MITRAB/INSS y autoridad sobre el 100% de colaboradores.', N'2026-10-25 03:58:30.955763', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Ingeniero electronico', N'Perfil histórico de soporte técnico, mantenimiento de infraestructura de cómputo, redes y equipos electrónicos de la panadería. (Puesto desactivado para nuevas contrataciones).', N'1. Diagnóstico y mantenimiento preventivo de equipos de cómputo y terminales del sistema.
2. Revisión de cableado de red y soporte en conectividad.', N'• Habilidad: Formación técnica en electrónica, redes o sistemas computacionales.
• Esfuerzo: Moderado de oficina y taller técnico.
• Responsabilidad: Soporte técnico sobre equipos asignados.', N'2026-10-25 03:58:31.205107', NULL, 0);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Jefe de Inventario', N'Garantizar el control exacto, resguardo y abastecimiento de las materias primas, insumos y productos de empaque, asegurando que el área de producción y ventas siempre cuente con los materiales necesarios sin incurrir en sobrestock o caducidad.', N'1. Recibir a los proveedores, verificar la calidad y cantidad de la materia prima recibida contra las órdenes de compra y facturas.
2. Ingresar y descargar diariamente los insumos en el sistema informático de la empresa, manteniendo el inventario teórico cuadrado con el físico.
3. Despachar la materia prima al área de producción utilizando el método PEPS (Primeras Entradas, Primeras Salidas).
4. Realizar inventarios físicos periódicos (semanales/mensuales) y emitir reportes de faltantes, mermas o productos próximos a vencer para la Gerencia.', N'• Habilidad: Bachiller técnico, estudiante o Licenciado en Administración, Contabilidad o Logística. Manejo avanzado de Excel y sistemas ERP/Inventario. Experiencia de 2 a 3 años en bodegas de alimentos. Organización espacial y capacidad analítica.
• Esfuerzo: Físico moderado a intenso (carga de sacos hasta 50 lbs, estibar cajas pesadas). Mental alto en cuadre numérico continuo y revisión de caducidades.
• Responsabilidad: Custodio absoluto de inventarios valorados en miles de córdobas; control de cuartos fríos y carretillas; estiba segura para evitar accidentes laborales.', N'2026-10-25 03:58:30.734182', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Limpieza', N'Mantener la higiene, limpieza y desinfección de todas las áreas de la panadería (producción, mostrador, mesas y oficinas), garantizando el cumplimiento de las normas de inocuidad alimentaria y creando un ambiente agradable y seguro para clientes y colaboradores.', N'1. Barrer, trapear y desinfectar continuamente el área de ventas, exhibidores y mesas de atención al cliente.
2. Realizar la limpieza profunda del área de producción (pisos, paredes, lavaderos y hornos externos) eliminando residuos de harina, grasas y azúcares.
3. Recolectar y clasificar los desechos sólidos del local, depositándolos en los basureros correspondientes.
4. Controlar y reportar el inventario de insumos de limpieza (cloro, desinfectantes, escobas, bolsas) para su oportuna reposición.', N'• Habilidad: Primaria completa o secundaria básica. Conocimiento en manejo y mezcla segura de químicos de limpieza básicos. Experiencia de 0 a 1 año en conserjería o limpieza. Sentido común para organizar tiempos y reportar averías.
• Esfuerzo: Físico intenso (de pie toda la jornada, agacharse, fregar superficies y cargar baldes/bolsas de basura). Esfuerzo mental mínimo y rutinario.
• Responsabilidad: Cuidado de utensilios de limpieza, uso racional de químicos sin desperdicio y colocación obligatoria de señalización de piso mojado.', N'2026-10-25 03:58:29.855474', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Maestro Panadero', N'Dirigir técnica y operativamente toda el área de producción, diseñando el menú de productos, estandarizando recetas y garantizando que todas las líneas de panadería y repostería cumplan con la más alta calidad, mientras entrena y supervisa a todo el equipo operativo.', N'1. Planificar la producción diaria y semanal según los pronósticos de ventas, asignando cargas de trabajo a cada nivel de panaderos.
2. Diseñar, costear y estandarizar nuevas recetas para ampliar el catálogo de productos de Brajher''s Cake.
3. Realizar auditorías de calidad continuas sobre las masas, tiempos de fermentación y producto terminado.
4. Capacitar técnicamente al personal de menor experiencia y resolver cualquier crisis operativa o fallo en equipos de producción de manera inmediata.', N'• Habilidad: Técnico Especialista o Maestro en Artes Culinarias, Panadería y Pastelería Internacional con sólidos conocimientos en química de alimentos y administración de cocinas. Más de 12 años dominando todas las áreas y liderando equipos. Visión innovadora y liderazgo.
• Esfuerzo: Físico moderado a intenso (supervisión y ejecuciones finas complejas). Mental muy intenso en balanceo de fórmulas, costeo de mermas y gestión operativa.
• Responsabilidad: Responsable técnico del taller industrial, rendimiento de materias primas, costos de producción, seguridad industrial y resultados de toda la cuadrilla.', N'2026-10-25 03:58:30.600038', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Panadero', N'Responsable de la preparación, amasado, fermentación y horneado de productos de panadería y repostería conforme a los estándares de calidad e inocuidad de Brajher''s Cake.', N'1. Elaborar masas para panes dulces, salados y repostería siguiendo recetas de la empresa.
2. Controlar tiempos de fermentación y temperaturas óptimas en hornos comerciales.
3. Coordinar con el equipo de producción para mantener el surtido continuo de producto fresco en vitrinas.
4. Mantener la limpieza y desinfección rigurosa de las áreas de trabajo y utensilios de amasado.', N'• Habilidad: Experiencia comprobable en panadería comercial, manejo de recetas tradicionales y destreza en manipulación de masas.
• Esfuerzo: Físico intenso en amasado continuo, manipulación de bandejas calientes y permanencia de pie.
• Responsabilidad: Cuidado de hornos y amasadoras industriales, optimización de ingredientes y cumplimiento de estándares de inocuidad.', N'2026-10-25 03:58:31.076273', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Panadero Aprendiz', N'Apoyar activamente en los procesos básicos de preparación, pesaje de ingredientes, amasado y horneado de productos, bajo la estricta dirección de los panaderos de mayor rango, asegurando el aprendizaje de las recetas y el cumplimiento de los estándares de calidad de Brajher''s Cake.', N'1. Pesar y medir con exactitud los ingredientes (harina, levadura, azúcar, sal) según las fichas técnicas y órdenes de producción del día.
2. Asistir en la carga y descarga de bandejas en los hornos y cuartos de fermentación.
3. Realizar el boleo manual, engrase de moldes y preparación de las bandejas para el proceso de horneado.
4. Limpiar y desinfectar sus mesas de trabajo, amasadoras y batidoras inmediatamente después de cada uso.', N'• Habilidad: Bachiller. Deseable cursos técnicos básicos en panadería o pastelería (INATEC) y nociones matemáticas de pesaje. Experiencia formativa de 0 a 1 año. Disposición y destreza manual básica.
• Esfuerzo: Físico intenso (de pie toda la jornada, amasado repetitivo y carga de sacos hasta 50 lbs). Esfuerzo mental regular en gramajes y tiempos de fermentación.
• Responsabilidad: Cuidado básico de básculas y amasadoras, cero desperdicio de materia prima y cumplimiento estricto de normas de higiene (redecillas y delantales).', N'2026-10-25 03:58:29.969131', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Panadero Junior', N'Ejecutar la preparación, amasado y horneado de productos de panadería y repostería tradicional, siguiendo las recetas estándar de la empresa, operando maquinaria industrial de manera independiente y brindando supervisión operativa al Panadero Aprendiz.', N'1. Elaborar masas para panes dulces, salados y repostería básica siguiendo con exactitud las fórmulas de producción diaria.
2. Operar independientemente hornos, amasadoras y cilindros, controlando tiempos de fermentación y temperaturas de cocción.
3. Decorar y presentar productos de repostería de complejidad media.
4. Orientar y corregir al Panadero Aprendiz en sus labores de pesaje, limpieza y preparación de bandejas.', N'• Habilidad: Bachiller. Técnico Medio en Panadería, Pastelería o Artes Culinarias (INATEC) con carnet de salud vigente. De 2 a 3 años de experiencia comprobable en producción y hornos comerciales. Detección de textura y consistencia de masas.
• Esfuerzo: Físico intenso (fuerza de amasado continuo y manipulación de bandejas calientes). Mental regular a alto en cálculo de cocción y memorización de recetas.
• Responsabilidad: Uso y programación adecuada de maquinaria industrial, control del rendimiento de masas para evitar mermas y supervisión del Aprendiz.', N'2026-10-25 03:58:30.240223', NULL, 1);
    INSERT INTO [rrhh].[PerfilesPuesto] ([Cargo], [PerfilPuesto], [Obligaciones], [RequisitosCompetencias], [ActualizadoEn], [ActualizadoPor], [Activo]) VALUES (N'Panadero Senior', N'Coordinar y ejecutar la producción diaria de las líneas de panadería y repostería fina, garantizando el estricto cumplimiento de la calidad, reduciendo mermas y dirigiendo al equipo operativo (Junior y Aprendiz) para cumplir con las metas de abastecimiento de las vitrinas.', N'1. Liderar la elaboración de productos complejos, repostería especializada, pasteles de vitrina y pedidos especiales de clientes.
2. Administrar el inventario de materias primas en piso de producción, calculando y solicitando los insumos necesarios para el turno.
3. Distribuir las tareas diarias entre el Junior y el Aprendiz, supervisando la calidad del amasado, fermentación y horneado en todo momento.
4. Realizar controles de calidad visual y gustativa antes de enviar el producto terminado al área de exhibición o despacho.', N'• Habilidad: Técnico Especialista en Panadería y Pastelería con formación en costeo de recetas y control de mermas. De 5 a 8 años de trayectoria liderando turnos. Creatividad, resolución de problemas y liderazgo bajo presión.
• Esfuerzo: Físico intenso (mesa, horno y supervisión en desplazamiento). Mental alto en coordinación simultánea de horneado y multiplicación de fórmulas.
• Responsabilidad: Custodia y reporte de mantenimiento de equipo mayor, alta responsabilidad económica en materia prima, seguridad del personal y calidad de producto.', N'2026-10-25 03:58:30.356466', NULL, 1);
END
GO

-- ============================================================================
-- Semilla para [ventas].[SecuenciasFiscales] (1 registros)
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [ventas].[SecuenciasFiscales])
BEGIN
    INSERT INTO [ventas].[SecuenciasFiscales] ([Serie], [Ultimo]) VALUES (N'FAC', 141);
END
GO

-- ============================================================================
-- Usuario Inicial SuperAdmin
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [seguridad].[Usuarios] WHERE [Username] = 'superadmin1')
BEGIN
    SET IDENTITY_INSERT [seguridad].[Usuarios] ON;
    INSERT INTO [seguridad].[Usuarios] ([ID], [NombreCompleto], [Username], [PasswordHash], [RolID], [Activo]) VALUES (12, N'Super Administrador 1', N'superadmin1', N'scrypt:32768:8:1$rgIeWwsOVS7ZoPvq$9dd0f74669093b2ce277470d32462329a56181f7ad823b293123245f785d80b9a22dbf128caf6aea2334606614c2c01756499812e428fe04e2cde439f699cd38', 1, 1);
    SET IDENTITY_INSERT [seguridad].[Usuarios] OFF;
END
GO


PRINT '============================================================================';
PRINT 'PanaderiaDB: Inicialización completa ejecutada con éxito.';
PRINT '63 Tablas | 8 Esquemas | 356+ Stored Procedures | 7 Roles RBAC | NIIF | Semilla';
PRINT '============================================================================';
GO

-- Modelo local y anónimo de mercadotecnia. Reaplicable sobre bases existentes.
IF OBJECT_ID(N'[crm].[ModeloMercadotecnia]', N'U') IS NULL
BEGIN
    CREATE TABLE [crm].[ModeloMercadotecnia] (
        [ID] INT NOT NULL CONSTRAINT [PK_ModeloMercadotecnia] PRIMARY KEY,
        [ModeloJSON] NVARCHAR(MAX) NOT NULL,
        [ModeloPublicoJSON] NVARCHAR(MAX) NOT NULL,
        [GeneradoEn] DATETIME2(0) NOT NULL,
        [FilasEntrenamiento] INT NOT NULL,
        CONSTRAINT [CK_ModeloMercadotecnia_Unico] CHECK ([ID] = 1),
        CONSTRAINT [CK_ModeloMercadotecnia_JSON] CHECK (ISJSON([ModeloJSON]) = 1),
        CONSTRAINT [CK_ModeloMercadotecnia_PublicoJSON] CHECK (ISJSON([ModeloPublicoJSON]) = 1),
        CONSTRAINT [CK_ModeloMercadotecnia_Filas] CHECK ([FilasEntrenamiento] >= 0)
    );
END;
GO

CREATE OR ALTER PROCEDURE [crm].[sp_DatosEntrenamientoMercadotecnia]
    @Desde DATETIME2(0)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    IF CONVERT(NVARCHAR(20), SESSION_CONTEXT(N'rol')) NOT IN (N'Admin', N'SuperAdmin')
        THROW 51070, 'Solo gerencia puede entrenar mercadotecnia.', 1;
    SELECT TOP (30000)
        f.ID AS FacturaID,
        f.FechaHora,
        df.ProductoID,
        df.Cantidad,
        df.Subtotal
    FROM [ventas].[Facturas] AS f
    INNER JOIN [ventas].[DetalleFacturas] AS df ON df.FacturaID = f.ID
    WHERE f.EstadoFiscal = 'Emitida'
      AND f.FechaHora >= @Desde
      AND df.Cantidad > 0
      AND df.Subtotal >= 0
    ORDER BY f.FechaHora DESC, f.ID DESC, df.ID DESC;
END;
GO

CREATE OR ALTER PROCEDURE [crm].[sp_GuardarModeloMercadotecnia]
    @ModeloJSON NVARCHAR(MAX),
    @ModeloPublicoJSON NVARCHAR(MAX),
    @FilasEntrenamiento INT
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    IF CONVERT(NVARCHAR(20), SESSION_CONTEXT(N'rol')) NOT IN (N'Admin', N'SuperAdmin')
        THROW 51071, 'Solo gerencia puede guardar modelos.', 1;
    IF ISJSON(@ModeloJSON) <> 1 OR DATALENGTH(@ModeloJSON) > 2097152
       OR ISJSON(@ModeloPublicoJSON) <> 1 OR DATALENGTH(@ModeloPublicoJSON) > 1048576
        THROW 51072, 'Modelo inválido o demasiado grande.', 1;
    IF @FilasEntrenamiento < 0
        THROW 51073, 'Conteo de entrenamiento inválido.', 1;
    UPDATE [crm].[ModeloMercadotecnia] WITH (UPDLOCK, HOLDLOCK)
    SET ModeloJSON = @ModeloJSON,
        ModeloPublicoJSON = @ModeloPublicoJSON,
        GeneradoEn = SYSDATETIME(),
        FilasEntrenamiento = @FilasEntrenamiento
    WHERE ID = 1;
    IF @@ROWCOUNT = 0
        INSERT INTO [crm].[ModeloMercadotecnia]
            (ID, ModeloJSON, ModeloPublicoJSON, GeneradoEn, FilasEntrenamiento)
        VALUES (1, @ModeloJSON, @ModeloPublicoJSON, SYSDATETIME(), @FilasEntrenamiento);
END;
GO

CREATE OR ALTER PROCEDURE [crm].[sp_LeerModeloMercadotecnia]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    IF CONVERT(NVARCHAR(20), SESSION_CONTEXT(N'rol')) NOT IN (N'Admin', N'SuperAdmin')
        THROW 51074, 'Solo gerencia puede leer el modelo completo.', 1;
    SELECT ModeloJSON, GeneradoEn, FilasEntrenamiento
    FROM [crm].[ModeloMercadotecnia]
    WHERE ID = 1;
END;
GO

CREATE OR ALTER PROCEDURE [crm].[sp_LeerModeloPublicoMercadotecnia]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ModeloPublicoJSON AS ModeloJSON, GeneradoEn
    FROM [crm].[ModeloMercadotecnia]
    WHERE ID = 1;
END;
GO

CREATE OR ALTER PROCEDURE [crm].[sp_HistorialPersonalMercadotecnia]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ClienteID INT = TRY_CONVERT(INT, SESSION_CONTEXT(N'usuario_id'));
    IF CONVERT(NVARCHAR(20), SESSION_CONTEXT(N'rol')) <> N'Cliente'
       OR @ClienteID IS NULL OR @ClienteID <= 1
       OR NOT EXISTS (SELECT 1 FROM [crm].[Clientes]
                      WHERE ID = @ClienteID AND EsInvitado = 0)
        RETURN;
    SELECT df.ProductoID, SUM(df.Cantidad) AS Unidades
    FROM [ventas].[Facturas] AS f
    INNER JOIN [ventas].[DetalleFacturas] AS df ON df.FacturaID = f.ID
    WHERE f.ClienteID = @ClienteID
      AND f.EstadoFiscal = 'Emitida'
      AND f.FechaHora >= DATEADD(DAY, -180, SYSDATETIME())
      AND df.Cantidad > 0
    GROUP BY df.ProductoID;
END;
GO

GRANT EXECUTE ON OBJECT::[crm].[sp_DatosEntrenamientoMercadotecnia] TO [db_rol_gerencia];
GRANT EXECUTE ON OBJECT::[crm].[sp_DatosEntrenamientoMercadotecnia] TO [db_rol_superadmin];
GRANT EXECUTE ON OBJECT::[crm].[sp_GuardarModeloMercadotecnia] TO [db_rol_gerencia];
GRANT EXECUTE ON OBJECT::[crm].[sp_GuardarModeloMercadotecnia] TO [db_rol_superadmin];
GRANT EXECUTE ON OBJECT::[crm].[sp_LeerModeloPublicoMercadotecnia] TO [db_rol_portal_cliente];
GRANT EXECUTE ON OBJECT::[crm].[sp_HistorialPersonalMercadotecnia] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_LeerModeloMercadotecnia] TO [db_rol_portal_cliente];
DENY EXECUTE ON OBJECT::[crm].[sp_LeerModeloMercadotecnia] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[crm].[sp_DatosEntrenamientoMercadotecnia] TO [db_rol_cajero_pos];
DENY EXECUTE ON OBJECT::[crm].[sp_GuardarModeloMercadotecnia] TO [db_rol_cajero_pos];
GO
