/* ============================================================================
   PANADERÍA Y REPOSTERÍA BRAJHER'S CAKE (PANADERÍA AMADA)
   ARCHIVO: 01_esquemas_migracion.sql
   PROPÓSITO:
     1. Separación física y lógica de la base de datos en 8 esquemas de dominio:
        - seguridad    (Autenticación, RBAC, 2FA, Auditoría, Bitácora de Errores, Bloqueos)
        - crm          (Fidelización, Clientes, Cotizaciones)
        - catalogo     (Categorías, Unidades de Medida, Productos, Ingredientes)
        - ventas       (TurnosCaja, Facturas, Detalles, Pagos, Encargos, Arqueos, Secuencias)
        - produccion   (Proveedores, MateriaPrima, Compras, Recetas, Lotes, Mermas)
        - rrhh         (Empleados, Turnos, Asistencia, Feriados, Nómina, Licencias, Vales)
        - contabilidad (Catálogo NIIF, Períodos, Asientos, CxC, CxP, Conciliación, Egresos)
        - fiscal       (BitacoraFiscal, DGI_Periodos, DGI_Revisiones, Observaciones, Exportaciones)
     2. Creación de tablas de seguridad avanzada (BitacoraErrores, BloqueosCuenta).
     3. Transferencia idempotente de tablas desde dbo hacia su esquema respectivo.
     4. Creación de sinónimos en dbo para compatibilidad retroactiva controlada.
     5. Triggers de inmutabilidad en tablas de auditoría, errores y documentos fiscales.
   ============================================================================ */

SET NOCOUNT ON;
GO

-- ============================================================================
-- 1. CREACIÓN IDEMPOTENTE DE LOS 8 ESQUEMAS DE DOMINIO (PROPIETARIO: dbo)
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
-- 2. GARANTIZAR EXISTENCIA DE TABLAS COMPLEMENTARIAS ANTES DE TRANSFERIR
-- ============================================================================
IF OBJECT_ID('seguridad.AuthChallenges', 'U') IS NULL AND OBJECT_ID('dbo.AuthChallenges', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[AuthChallenges] (
        Token VARCHAR(64) NOT NULL PRIMARY KEY,
        Kind VARCHAR(20) NOT NULL,
        Subject VARCHAR(32) NOT NULL,
        Verifier VARCHAR(64) NOT NULL DEFAULT '',
        Secret VARCHAR(64) NOT NULL DEFAULT '',
        Binding VARCHAR(64) NOT NULL DEFAULT '',
        ExpiresAt BIGINT NOT NULL,
        Attempts INT NOT NULL DEFAULT 0,
        Verified BIT NOT NULL DEFAULT 0,
        Consumed BIT NOT NULL DEFAULT 0,
        CONSTRAINT CK_AuthChallenges_Kind CHECK (Kind IN ('sms', 'totp_enroll', 'totp_login')),
        CONSTRAINT CK_AuthChallenges_Attempts CHECK (Attempts >= 0)
    );
    CREATE INDEX IX_AuthChallenges_Subject_Kind ON [seguridad].[AuthChallenges] (Subject, Kind);
END
GO

IF OBJECT_ID('ventas.SecuenciasFiscales', 'U') IS NULL AND OBJECT_ID('dbo.SecuenciasFiscales', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[SecuenciasFiscales] (
        Serie VARCHAR(10) PRIMARY KEY,
        Ultimo BIGINT NOT NULL DEFAULT 0
    );
END
GO

IF OBJECT_ID('fiscal.BitacoraFiscal', 'U') IS NULL AND OBJECT_ID('dbo.BitacoraFiscal', 'U') IS NULL
BEGIN
    CREATE TABLE [fiscal].[BitacoraFiscal] (
        ID BIGINT IDENTITY PRIMARY KEY,
        Fecha DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        UsuarioID INT NULL,
        Accion NVARCHAR(50) NOT NULL,
        Entidad NVARCHAR(50) NOT NULL,
        EntidadID INT NULL,
        Detalle NVARCHAR(MAX) NOT NULL,
        IP VARCHAR(45) NULL
    );
END
GO

IF OBJECT_ID('ventas.ArqueoDetalleDenominacion', 'U') IS NULL AND OBJECT_ID('dbo.ArqueoDetalleDenominacion', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[ArqueoDetalleDenominacion] (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        ArqueoID INT NOT NULL,
        TipoMoneda VARCHAR(10) NOT NULL DEFAULT 'NIO',
        Denominacion DECIMAL(12,2) NOT NULL,
        Cantidad INT NOT NULL DEFAULT 0,
        Subtotal AS (Denominacion * Cantidad) PERSISTED
    );
END
GO

IF OBJECT_ID('ventas.ArqueoAuditLog', 'U') IS NULL AND OBJECT_ID('dbo.ArqueoAuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE [ventas].[ArqueoAuditLog] (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        ArqueoID INT NOT NULL,
        UsuarioID INT NOT NULL,
        Accion VARCHAR(50) NOT NULL,
        Detalle VARCHAR(500) NULL,
        FechaAccion DATETIME NOT NULL DEFAULT GETDATE(),
        DireccionIP VARCHAR(45) NULL
    );
END
GO

-- ============================================================================
-- 3. CREACIÓN DE NUEVAS TABLAS DE SEGURIDAD AVANZADA Y ALERTAS SMTP
-- ============================================================================
IF OBJECT_ID('seguridad.BitacoraErrores', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[BitacoraErrores] (
        ID BIGINT IDENTITY(1,1) PRIMARY KEY,
        FechaHora DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        Origen VARCHAR(30) NOT NULL DEFAULT 'SQL_SP', -- 'SQL_SP', 'SQL_TRIGGER', 'PYTHON_DB', 'SEGURIDAD_AUTH', 'HTTP_500'
        Severidad VARCHAR(15) NOT NULL DEFAULT 'ERROR', -- 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        NumeroError INT NULL,
        EstadoError INT NULL,
        LineaError INT NULL,
        Procedimiento NVARCHAR(128) NULL,
        EsquemaOrigen NVARCHAR(64) NULL,
        MensajeError NVARCHAR(2000) NOT NULL,
        DetalleTecnico NVARCHAR(MAX) NULL,
        ParametrosJSON NVARCHAR(MAX) NULL,
        UsuarioID INT NULL,
        Username NVARCHAR(100) NULL,
        RolAplicacion NVARCHAR(50) NULL,
        UsuarioBD NVARCHAR(128) NOT NULL DEFAULT ORIGINAL_LOGIN(),
        DireccionIP VARCHAR(45) NULL,
        RutaHTTP NVARCHAR(255) NULL,
        NotificadoSMTP BIT NOT NULL DEFAULT 0,
        FechaNotificacion DATETIME2 NULL,
        CONSTRAINT CK_BitacoraErrores_Severidad CHECK (Severidad IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL'))
    );
    CREATE INDEX IX_BitacoraErrores_FechaHora ON [seguridad].[BitacoraErrores] (FechaHora DESC);
    CREATE INDEX IX_BitacoraErrores_Notificado ON [seguridad].[BitacoraErrores] (NotificadoSMTP, Severidad);
END
GO

IF OBJECT_ID('seguridad.BloqueosCuenta', 'U') IS NULL
BEGIN
    CREATE TABLE [seguridad].[BloqueosCuenta] (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        Identificador NVARCHAR(100) NOT NULL, -- Username o Teléfono
        DireccionIP VARCHAR(45) NOT NULL,
        IntentosFallidos INT NOT NULL DEFAULT 1,
        PrimerIntento DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        UltimoIntento DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        BloqueadoHasta DATETIME2 NULL,
        Motivo NVARCHAR(255) NULL,
        CONSTRAINT UX_BloqueosCuenta_Identificador_IP UNIQUE (Identificador, DireccionIP)
    );
    CREATE INDEX IX_BloqueosCuenta_BloqueadoHasta ON [seguridad].[BloqueosCuenta] (Identificador, BloqueadoHasta);
END
GO

-- ============================================================================
-- 4. TRANSFERENCIA IDEMPOTENTE DE LAS TABLAS A SUS 8 ESQUEMAS DE DOMINIO
--    Y CREACIÓN DE SINÓNIMOS EN [dbo] PARA COMPATIBILIDAD RETROACTIVA
-- ============================================================================
DECLARE @MapaTablas TABLE (
    EsquemaDestino SYSNAME NOT NULL,
    NombreTabla SYSNAME NOT NULL
);

INSERT INTO @MapaTablas (EsquemaDestino, NombreTabla) VALUES
-- 1. Esquema: seguridad
('seguridad', 'Roles'),
('seguridad', 'Usuarios'),
('seguridad', 'AuthChallenges'),
('seguridad', 'AuditLog'),
('seguridad', 'ConfiguracionSistema'),
('seguridad', 'BitacoraErrores'),
('seguridad', 'BloqueosCuenta'),
-- 2. Esquema: crm
('crm', 'NivelesConfianza'),
('crm', 'Clientes'),
('crm', 'Cotizaciones'),
-- 3. Esquema: catalogo
('catalogo', 'Categorias'),
('catalogo', 'UnidadesMedida'),
('catalogo', 'Productos'),
('catalogo', 'Ingredientes'),
-- 4. Esquema: ventas
('ventas', 'TurnosCaja'),
('ventas', 'Facturas'),
('ventas', 'DetalleFacturas'),
('ventas', 'DetalleIngredientes'),
('ventas', 'Pagos'),
('ventas', 'FacturasRUC'),
('ventas', 'Encargos'),
('ventas', 'ArqueoCaja'),
('ventas', 'ArqueoDetalleDenominacion'),
('ventas', 'ArqueoAuditLog'),
('ventas', 'TipoCambio'),
('ventas', 'SecuenciasFiscales'),
-- 5. Esquema: produccion
('produccion', 'Proveedores'),
('produccion', 'MateriaPrima'),
('produccion', 'ComprasMateriaPrima'),
('produccion', 'RecetaProducto'),
('produccion', 'ProduccionLotes'),
('produccion', 'ConsumoLote'),
('produccion', 'Mermas'),
-- 6. Esquema: rrhh
('rrhh', 'Empleados'),
('rrhh', 'TurnosLaborales'),
('rrhh', 'Asistencia'),
('rrhh', 'FeriadosNacionales'),
('rrhh', 'Nomina'),
('rrhh', 'DetalleNomina'),
('rrhh', 'LicenciasEmpleados'),
('rrhh', 'DeduccionesJudiciales'),
('rrhh', 'IncidentesLaborales'),
('rrhh', 'ValesEmpleados'),
-- 7. Esquema: contabilidad
('contabilidad', 'CatalogoCuentas'),
('contabilidad', 'PeriodosContables'),
('contabilidad', 'TiposComprobante'),
('contabilidad', 'AsientosDiario'),
('contabilidad', 'DetalleAsientos'),
('contabilidad', 'EgresosPrivados'),
('contabilidad', 'CuentasPorCobrar'),
('contabilidad', 'CuentasPorPagar'),
('contabilidad', 'PagosCxC'),
('contabilidad', 'ConciliacionBancaria'),
('contabilidad', 'DetalleConciliacion'),
-- 8. Esquema: fiscal
('fiscal', 'BitacoraFiscal'),
('fiscal', 'DGI_Periodos'),
('fiscal', 'DGI_Revisiones'),
('fiscal', 'DGI_Observaciones'),
('fiscal', 'DGI_Exportaciones');

DECLARE @Esquema SYSNAME, @Tabla SYSNAME, @SQL NVARCHAR(MAX);

DECLARE cur_migracion CURSOR LOCAL FAST_FORWARD FOR
    SELECT EsquemaDestino, NombreTabla FROM @MapaTablas;

OPEN cur_migracion;
FETCH NEXT FROM cur_migracion INTO @Esquema, @Tabla;

WHILE @@FETCH_STATUS = 0
BEGIN
    -- Si la tabla física aún está en dbo y no existe como tabla en el esquema destino:
    IF OBJECT_ID(N'[dbo].[' + @Tabla + N']', 'U') IS NOT NULL
       AND OBJECT_ID(N'[' + @Esquema + N'].[' + @Tabla + N']', 'U') IS NULL
    BEGIN
        -- Si por alguna razón hubiera un sinónimo previo, eliminarlo antes de transferir
        IF OBJECT_ID(N'[dbo].[' + @Tabla + N']', 'SN') IS NOT NULL
        BEGIN
            SET @SQL = N'DROP SYNONYM [dbo].[' + @Tabla + N']';
            EXEC sp_executesql @SQL;
        END

        SET @SQL = N'ALTER SCHEMA [' + @Esquema + N'] TRANSFER [dbo].[' + @Tabla + N']';
        EXEC sp_executesql @SQL;
    END

    -- Si la tabla ya existe en su esquema destino y no hay sinónimo en dbo, crearlo:
    IF OBJECT_ID(N'[' + @Esquema + N'].[' + @Tabla + N']', 'U') IS NOT NULL
       AND OBJECT_ID(N'[dbo].[' + @Tabla + N']', 'SN') IS NULL
       AND OBJECT_ID(N'[dbo].[' + @Tabla + N']', 'U') IS NULL
    BEGIN
        SET @SQL = N'CREATE SYNONYM [dbo].[' + @Tabla + N'] FOR [' + @Esquema + N'].[' + @Tabla + N']';
        EXEC sp_executesql @SQL;
    END

    FETCH NEXT FROM cur_migracion INTO @Esquema, @Tabla;
END

CLOSE cur_migracion;
DEALLOCATE cur_migracion;
GO

-- ============================================================================
-- 5. CONFIGURACIONES POR DEFECTO DE SEGURIDAD Y ALERTAS SMTP + COLUMNAS ADITIVAS
-- ============================================================================
IF OBJECT_ID('crm.Cotizaciones', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('crm.Cotizaciones', 'NombreContacto') IS NULL
        EXEC('ALTER TABLE [crm].[Cotizaciones] ADD [NombreContacto] VARCHAR(150) NULL');
END
GO

IF OBJECT_ID('catalogo.Productos', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('catalogo.Productos', 'TasaIVA') IS NULL
        EXEC('ALTER TABLE [catalogo].[Productos] ADD [TasaIVA] DECIMAL(5,2) NULL');
    IF COL_LENGTH('catalogo.Productos', 'MotivoExencion') IS NULL
        EXEC('ALTER TABLE [catalogo].[Productos] ADD [MotivoExencion] NVARCHAR(200) NULL');
END
GO

IF OBJECT_ID('ventas.Facturas', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('ventas.Facturas', 'EstadoFiscal') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [EstadoFiscal] VARCHAR(12) NOT NULL DEFAULT ''Emitida''');
    IF COL_LENGTH('ventas.Facturas', 'DocumentoJSON') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [DocumentoJSON] NVARCHAR(MAX) NULL');
    IF COL_LENGTH('ventas.Facturas', 'AnuladaPor') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [AnuladaPor] INT NULL');
    IF COL_LENGTH('ventas.Facturas', 'FechaAnulacion') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [FechaAnulacion] DATETIME NULL');
    IF COL_LENGTH('ventas.Facturas', 'MotivoAnulacion') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [MotivoAnulacion] NVARCHAR(300) NULL');
    IF COL_LENGTH('ventas.Facturas', 'ClaveSolicitud') IS NULL
        EXEC('ALTER TABLE [ventas].[Facturas] ADD [ClaveSolicitud] VARCHAR(64) NULL');
END
GO

IF OBJECT_ID('ventas.ArqueoCaja', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('ventas.ArqueoCaja', 'VerificadoPorID') IS NULL
        EXEC('ALTER TABLE [ventas].[ArqueoCaja] ADD [VerificadoPorID] INT NULL');
    IF COL_LENGTH('ventas.ArqueoCaja', 'FechaVerificacion') IS NULL
        EXEC('ALTER TABLE [ventas].[ArqueoCaja] ADD [FechaVerificacion] DATETIME NULL');
    IF COL_LENGTH('ventas.ArqueoCaja', 'EstadoArqueo') IS NULL
        EXEC('ALTER TABLE [ventas].[ArqueoCaja] ADD [EstadoArqueo] VARCHAR(20) NULL DEFAULT ''Cerrado''');
    IF COL_LENGTH('ventas.ArqueoCaja', 'NotasDiscrepancia') IS NULL
        EXEC('ALTER TABLE [ventas].[ArqueoCaja] ADD [NotasDiscrepancia] VARCHAR(500) NULL');
    IF COL_LENGTH('ventas.ArqueoCaja', 'RequiereJustificacion') IS NULL
        EXEC('ALTER TABLE [ventas].[ArqueoCaja] ADD [RequiereJustificacion] BIT NOT NULL DEFAULT 0');
END
GO

IF OBJECT_ID('rrhh.Empleados', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('rrhh.Empleados', 'FaceDescriptor') IS NULL
        EXEC('ALTER TABLE [rrhh].[Empleados] ADD [FaceDescriptor] NVARCHAR(MAX) NULL');
    IF COL_LENGTH('rrhh.Empleados', 'HoraEntrada') IS NULL
        EXEC('ALTER TABLE [rrhh].[Empleados] ADD [HoraEntrada] TIME NULL');
    IF COL_LENGTH('rrhh.Empleados', 'HoraSalida') IS NULL
        EXEC('ALTER TABLE [rrhh].[Empleados] ADD [HoraSalida] TIME NULL');
END
GO

IF OBJECT_ID('contabilidad.CatalogoCuentas', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('contabilidad.CatalogoCuentas', 'Nivel') IS NULL
        EXEC('ALTER TABLE [contabilidad].[CatalogoCuentas] ADD [Nivel] TINYINT NOT NULL DEFAULT 4');
    IF COL_LENGTH('contabilidad.CatalogoCuentas', 'CuentaPadreID') IS NULL
        EXEC('ALTER TABLE [contabilidad].[CatalogoCuentas] ADD [CuentaPadreID] INT NULL');
    IF COL_LENGTH('contabilidad.CatalogoCuentas', 'EsTransaccional') IS NULL
        EXEC('ALTER TABLE [contabilidad].[CatalogoCuentas] ADD [EsTransaccional] BIT NOT NULL DEFAULT 1');
    IF COL_LENGTH('contabilidad.CatalogoCuentas', 'Descripcion') IS NULL
        EXEC('ALTER TABLE [contabilidad].[CatalogoCuentas] ADD [Descripcion] VARCHAR(255) NULL');
    IF COL_LENGTH('contabilidad.CatalogoCuentas', 'OrdenVisualizacion') IS NULL
        EXEC('ALTER TABLE [contabilidad].[CatalogoCuentas] ADD [OrdenVisualizacion] INT NOT NULL DEFAULT 0');
END
GO

IF OBJECT_ID('contabilidad.AsientosDiario', 'U') IS NOT NULL
BEGIN
    IF COL_LENGTH('contabilidad.AsientosDiario', 'TipoComprobanteID') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [TipoComprobanteID] INT NULL');
    IF COL_LENGTH('contabilidad.AsientosDiario', 'NumeroComprobante') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [NumeroComprobante] VARCHAR(20) NULL');
    IF COL_LENGTH('contabilidad.AsientosDiario', 'IP') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [IP] VARCHAR(45) NULL');
    IF COL_LENGTH('contabilidad.AsientosDiario', 'AnuladoPor') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [AnuladoPor] INT NULL');
    IF COL_LENGTH('contabilidad.AsientosDiario', 'FechaAnulacion') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [FechaAnulacion] DATETIME NULL');
    IF COL_LENGTH('contabilidad.AsientosDiario', 'MotivoAnulacion') IS NULL
        EXEC('ALTER TABLE [contabilidad].[AsientosDiario] ADD [MotivoAnulacion] VARCHAR(255) NULL');
END
GO

IF OBJECT_ID('fiscal.DGI_Periodos', 'U') IS NULL AND OBJECT_ID('seguridad.Usuarios', 'U') IS NOT NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Periodos] (
        ID INT IDENTITY PRIMARY KEY,
        Desde DATE NOT NULL,
        Hasta DATE NOT NULL,
        Estado VARCHAR(12) NOT NULL DEFAULT 'Abierto',
        CreadoPor INT NOT NULL REFERENCES [seguridad].[Usuarios](ID),
        CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_DGI_PeriodoFechas CHECK (Hasta >= Desde),
        CONSTRAINT CK_DGI_PeriodoEstado CHECK (Estado IN ('Abierto', 'Cerrado')),
        CONSTRAINT UX_DGI_Periodo UNIQUE (Desde, Hasta)
    );
    IF OBJECT_ID('dbo.DGI_Periodos', 'SN') IS NULL
        EXEC('CREATE SYNONYM [dbo].[DGI_Periodos] FOR [fiscal].[DGI_Periodos]');
END
GO

IF OBJECT_ID('fiscal.DGI_Revisiones', 'U') IS NULL AND OBJECT_ID('fiscal.DGI_Periodos', 'U') IS NOT NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Revisiones] (
        ID INT IDENTITY PRIMARY KEY,
        PeriodoID INT NOT NULL REFERENCES [fiscal].[DGI_Periodos](ID),
        Obligacion NVARCHAR(200) NOT NULL,
        Version INT NOT NULL,
        Motor VARCHAR(30) NOT NULL,
        Huella CHAR(64) NOT NULL,
        SnapshotJSON NVARCHAR(MAX) NOT NULL,
        ResultadoJSON NVARCHAR(MAX) NOT NULL,
        Estado VARCHAR(15) NOT NULL DEFAULT 'BORRADOR',
        CreadoPor INT NOT NULL REFERENCES [seguridad].[Usuarios](ID),
        CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        RevisadoPor INT NULL REFERENCES [seguridad].[Usuarios](ID),
        RevisadoEn DATETIME2 NULL,
        NotaRevision NVARCHAR(1000) NULL,
        AprobadoPor INT NULL REFERENCES [seguridad].[Usuarios](ID),
        AprobadoEn DATETIME2 NULL,
        CONSTRAINT CK_DGI_RevisionEstado CHECK (Estado IN ('BORRADOR', 'EN_REVISION', 'APROBADO', 'EXPORTADO', 'OBSOLETO')),
        CONSTRAINT UX_DGI_Revision UNIQUE (PeriodoID, Obligacion, Version)
    );
    IF OBJECT_ID('dbo.DGI_Revisiones', 'SN') IS NULL
        EXEC('CREATE SYNONYM [dbo].[DGI_Revisiones] FOR [fiscal].[DGI_Revisiones]');
END
GO

IF OBJECT_ID('fiscal.DGI_Observaciones', 'U') IS NULL AND OBJECT_ID('fiscal.DGI_Revisiones', 'U') IS NOT NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Observaciones] (
        ID INT IDENTITY PRIMARY KEY,
        RevisionID INT NOT NULL REFERENCES [fiscal].[DGI_Revisiones](ID),
        Hallazgo CHAR(24) NOT NULL,
        Comentario NVARCHAR(1000) NOT NULL,
        UsuarioID INT NOT NULL REFERENCES [seguridad].[Usuarios](ID),
        Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    IF OBJECT_ID('dbo.DGI_Observaciones', 'SN') IS NULL
        EXEC('CREATE SYNONYM [dbo].[DGI_Observaciones] FOR [fiscal].[DGI_Observaciones]');
END
GO

IF OBJECT_ID('fiscal.DGI_Exportaciones', 'U') IS NULL AND OBJECT_ID('fiscal.DGI_Revisiones', 'U') IS NOT NULL
BEGIN
    CREATE TABLE [fiscal].[DGI_Exportaciones] (
        ID INT IDENTITY PRIMARY KEY,
        RevisionID INT NOT NULL REFERENCES [fiscal].[DGI_Revisiones](ID),
        Nombre NVARCHAR(150) NOT NULL,
        SHA256 CHAR(64) NOT NULL,
        Archivo VARBINARY(MAX) NOT NULL,
        UsuarioID INT NOT NULL REFERENCES [seguridad].[Usuarios](ID),
        Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    IF OBJECT_ID('dbo.DGI_Exportaciones', 'SN') IS NULL
        EXEC('CREATE SYNONYM [dbo].[DGI_Exportaciones] FOR [fiscal].[DGI_Exportaciones]');
END
GO

IF OBJECT_ID('seguridad.ConfiguracionSistema', 'U') IS NOT NULL
BEGIN
    DECLARE @Defaults TABLE (Clave NVARCHAR(100), Valor NVARCHAR(MAX), Descripcion NVARCHAR(255));
    INSERT INTO @Defaults VALUES
    ('smtp_alertas_activo', '1', 'Activar notificaciones de errores y alertas críticas por correo SMTP (1=Sí, 0=No)'),
    ('smtp_nivel_minimo', 'ERROR', 'Nivel mínimo para envío de alertas por correo (WARNING, ERROR, CRITICAL)'),
    ('smtp_bloqueo_intentos_max', '5', 'Número máximo de intentos fallidos de login antes de bloquear cuenta y alertar por SMTP'),
    ('smtp_bloqueo_minutos', '15', 'Minutos de bloqueo automático tras exceder intentos fallidos de login');

    INSERT INTO [seguridad].[ConfiguracionSistema] (Clave, Valor, Descripcion)
    SELECT d.Clave, d.Valor, d.Descripcion
    FROM @Defaults d
    WHERE NOT EXISTS (SELECT 1 FROM [seguridad].[ConfiguracionSistema] c WHERE c.Clave = d.Clave);
END
GO

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
