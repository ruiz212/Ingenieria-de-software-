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
