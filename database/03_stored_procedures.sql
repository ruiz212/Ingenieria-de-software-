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
    SELECT Cargo, PerfilPuesto, Obligaciones, RequisitosCompetencias, ActualizadoEn, Activo
    FROM [rrhh].[PerfilesPuesto] ORDER BY Cargo;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_CambiarEstadoPerfilPuesto]
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

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEscalaSalarialPorCargo]
    @Cargo NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CargoClean NVARCHAR(100) = LTRIM(RTRIM(@Cargo));

    IF EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) = LOWER(@CargoClean))
    BEGIN
        SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
        FROM [rrhh].[escala_salarial]
        WHERE LOWER(cargo) = LOWER(@CargoClean);
        RETURN;
    END

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

    SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
    FROM [rrhh].[escala_salarial]
    WHERE LOWER(cargo) LIKE '%' + LOWER(@CargoClean) + '%'
       OR LOWER(@CargoClean) LIKE '%' + LOWER(cargo) + '%'
    ORDER BY id ASC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEscalaSalarial]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
    FROM [rrhh].[escala_salarial]
    ORDER BY id ASC;
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
CREATE OR ALTER PROCEDURE [rrhh].[sp_CambiarEstadoPerfilPuesto]
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
CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEscalaSalarial]
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
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEscalaSalarialPorCargo]
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
-- REMEDIACIÓN AUDITORÍA DE REGLAS DE NEGOCIO (2026-10-25: L01-L28)
-- ============================================================================

-- >>> sql_group1_pos_kds_fiscal.sql
-- ============================================================================
-- REMEDIACIÓN GRUPO 1: POS, Arqueos, Encargos/KDS, Cotizaciones y Anulaciones Fiscales
-- Hallazgos: L01, L02, L03, L13, L15, L28
-- ============================================================================

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET NOCOUNT ON;
GO

-- ----------------------------------------------------------------------------
-- L13: Cálculo consistente del efectivo esperado de la gaveta del turno POS
-- Distingue la gaveta operativa del turno POS (ventas.Pagos por TurnoReceptorID,
-- incluyendo cobros en efectivo y restando devoluciones/anulaciones del turno)
-- respecto de Caja General de oficina (EgresosPrivados / ValesEmpleados).
-- ----------------------------------------------------------------------------
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
    FROM [ventas].[Pagos] p
    WHERE p.TurnoReceptorID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerResumenTurnoCaja]
    @TurnoID INT
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM [ventas].[Pagos] p JOIN [ventas].[Facturas] f ON f.ID=p.FacturaID
               JOIN [ventas].[TurnosCaja] t ON t.ID=@TurnoID
               WHERE p.Monto<>0 AND (p.TurnoReceptorID IS NULL OR p.UsuarioReceptorID IS NULL)
                 AND (f.TurnoID=@TurnoID OR (p.FechaPago>=t.FechaApertura AND (t.FechaCierre IS NULL OR p.FechaPago<=t.FechaCierre))))
        THROW 51021, 'Existen movimientos históricos sin receptor de caja. Conciliar antes del arqueo.', 1;

    SELECT
        ISNULL(SUM(CASE WHEN (p.MetodoPago = 'Efectivo' OR (p.MetodoPago='Efectivo USD' AND p.MonedaRegistro='NIO')) THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' AND p.MonedaRegistro<>'NIO' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
    FROM [ventas].[Pagos] p
    WHERE p.TurnoReceptorID = @TurnoID;
END
GO

IF DATABASE_PRINCIPAL_ID('db_rol_cajero_pos') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_cajero_pos];
IF DATABASE_PRINCIPAL_ID('db_rol_gerencia') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_gerencia];
IF DATABASE_PRINCIPAL_ID('db_rol_superadmin') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_superadmin];
GO

-- ----------------------------------------------------------------------------
-- L03: Máquina de estados estricta para encargos en KDS y bloqueo de pago duplicado
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarEstadoEncargoCompare]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    DECLARE @FacturaID INT;
    SELECT @FacturaID = ID FROM [ventas].[Facturas] WITH(UPDLOCK, HOLDLOCK)
      WHERE CodigoSeguimiento = @P2 AND EstadoFiscal = 'Emitida';

    IF @FacturaID IS NOT NULL
    BEGIN
        DECLARE @EstadoActual NVARCHAR(50);
        SELECT @EstadoActual = Estado FROM [ventas].[Encargos] WITH(UPDLOCK, HOLDLOCK)
          WHERE FacturaID = @FacturaID;

        DECLARE @EstadoDestino NVARCHAR(50) = CASE WHEN @P1 = N'En Preparacion' THEN N'En Proceso' ELSE @P1 END;
        DECLARE @EstadoEsperado NVARCHAR(50) = CASE WHEN @P3 = N'En Preparacion' THEN N'En Proceso' ELSE @P3 END;

        IF (@EstadoActual = N'Entregado' OR @EstadoEsperado = N'Entregado') AND @EstadoDestino <> N'Entregado'
            THROW 51034, 'Un encargo ya entregado es estado terminal en KDS y no puede revertirse ni cancelarse.', 1;

        IF @EstadoActual IN (N'Cancelado', N'Anulada') OR @EstadoEsperado IN (N'Cancelado', N'Anulada')
            THROW 51034, 'Un encargo cancelado o anulado no admite transiciones.', 1;

        IF NOT (
            (@EstadoEsperado = N'Pendiente' AND @EstadoDestino IN (N'En Proceso', N'Listo', N'Entregado'))
            OR (@EstadoEsperado = N'En Proceso' AND @EstadoDestino IN (N'Listo', N'Entregado'))
            OR (@EstadoEsperado = N'Listo' AND @EstadoDestino IN (N'Entregado'))
            OR (@EstadoEsperado = @EstadoDestino AND @EstadoDestino IN (N'Pendiente', N'En Proceso', N'Listo', N'Entregado'))
        )
            THROW 51034, 'Transición de estado de encargo inválida o regresiva.', 1;

        IF @EstadoDestino = N'Entregado' AND IS_MEMBER('db_rol_produccion') = 1 AND EXISTS (
            SELECT 1 FROM [ventas].[Facturas] f WHERE f.ID = @FacturaID AND
              f.Total > ISNULL((SELECT SUM(p.Monto) FROM [ventas].[Pagos] p WHERE p.FacturaID = f.ID), 0))
            THROW 51032, 'El cobro pendiente debe confirmarlo un cajero con turno abierto.', 1;

        UPDATE e SET Estado = @EstadoDestino
        FROM [ventas].[Encargos] AS e
        JOIN [ventas].[Facturas] AS f ON e.FacturaID = f.ID
        WHERE f.ID = @FacturaID AND f.EstadoFiscal = 'Emitida' AND e.Estado = @EstadoEsperado;
    END
    ELSE
    BEGIN
        UPDATE e SET Estado = @P1
        FROM [ventas].[Encargos] AS e
        JOIN [ventas].[Facturas] AS f ON e.FacturaID = f.ID
        WHERE f.ID = @FacturaID AND f.EstadoFiscal = 'Emitida' AND e.Estado = @P3;
    END
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
    SET @UsuarioReceptorID = COALESCE(@UsuarioReceptorID, TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT));
    DECLARE @TotalFactura DECIMAL(18, 2);
    SELECT @TotalFactura = Total FROM [ventas].[Facturas] WITH(UPDLOCK, HOLDLOCK) WHERE ID = @P1 AND EstadoFiscal = 'Emitida';
    IF @TotalFactura IS NULL
        THROW 51025, 'La factura no está emitida.', 1;

    DECLARE @PagadoActual DECIMAL(18, 2);
    SELECT @PagadoActual = ISNULL(SUM(Monto), 0) FROM [ventas].[Pagos] WITH(UPDLOCK, HOLDLOCK) WHERE FacturaID = @P1;
    IF @P3 IS NULL OR @P3 <= 0 OR (@PagadoActual + @P3) > @TotalFactura
        THROW 51035, 'El encargo ya fue pagado o el monto excede el saldo pendiente.', 1;

    IF @TurnoReceptorID IS NULL
        SELECT TOP 1 @TurnoReceptorID = ID FROM [ventas].[TurnosCaja] WITH(UPDLOCK, HOLDLOCK)
        WHERE UsuarioID = @UsuarioReceptorID AND Cerrado = 0 ORDER BY ID DESC;
    IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK, HOLDLOCK) WHERE ID = @TurnoReceptorID AND UsuarioID = @UsuarioReceptorID AND Cerrado = 0)
        THROW 51026, 'El saldo requiere la caja abierta del usuario receptor.', 1;
    IF EXISTS (SELECT 1 FROM [ventas].[ArqueoCaja] WHERE TurnoID = @TurnoReceptorID AND EstadoArqueo IN ('Pendiente', 'Verificado'))
        THROW 51027, 'La caja receptora tiene un arqueo pendiente.', 1;

    INSERT INTO [ventas].[Pagos] (FacturaID, MetodoPago, Monto, NombreTransferente, FechaPago, MonedaRegistro, TipoCambioAplicado, TurnoReceptorID, UsuarioReceptorID)
    VALUES (@P1, @P2, @P3, @P4, @P5, 'NIO', @P6, @TurnoReceptorID, @UsuarioReceptorID);
END
GO

-- ----------------------------------------------------------------------------
-- L15: Vínculo único de cotización a factura (uso único con bloqueo transaccional)
-- ----------------------------------------------------------------------------
IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = 'CK_Cotizaciones_Estado'
      AND parent_object_id = OBJECT_ID('crm.Cotizaciones')
)
BEGIN
    ALTER TABLE [crm].[Cotizaciones] DROP CONSTRAINT [CK_Cotizaciones_Estado];
END
GO

ALTER TABLE [crm].[Cotizaciones] WITH CHECK ADD CONSTRAINT [CK_Cotizaciones_Estado]
    CHECK ([Estado] IN ('Pendiente', 'Cotizada', 'Aceptada', 'Facturada', 'Rechazada'));
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionParaCalculoVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Especificaciones, PrecioCotizado
    FROM [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID = @P1
      AND Estado IN ('Cotizada', 'Aceptada')
      AND PrecioCotizado IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM [ventas].[Facturas] f WITH (UPDLOCK, HOLDLOCK)
          WHERE f.EstadoFiscal = 'Emitida'
            AND f.DocumentoJSON IS NOT NULL
            AND ISJSON(f.DocumentoJSON) = 1
            AND EXISTS (
                SELECT 1
                FROM OPENJSON(f.DocumentoJSON, '$.productos')
                WHERE TRY_CAST(JSON_VALUE([value], '$.cotizacion_id') AS INT) = @P1
            )
      );
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_MarcarCotizacionAceptadaEnVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
    SET Estado = 'Facturada'
    WHERE ID = @P1
      AND Estado IN ('Cotizada', 'Aceptada')
      AND PrecioCotizado IS NOT NULL;
    IF @@ROWCOUNT <> 1
        THROW 51036, 'La cotización personalizada ya fue facturada o no está disponible para venta.', 1;
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

        IF EXISTS (SELECT 1 FROM [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @CotizacionID AND Estado = 'Facturada')
            THROW 52028, 'La cotización ya fue facturada y no puede reutilizarse ni cambiar de estado.', 1;

        UPDATE [crm].[Cotizaciones]
        SET Estado = @NuevoEstado,
            PrecioCotizado = ISNULL(@PrecioCotizado, PrecioCotizado)
        WHERE ID = @CotizacionID
          AND Estado <> 'Facturada';
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_ActualizarEstadoCotizacion';
        THROW;
    END CATCH
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

            IF @CotID IS NOT NULL
            BEGIN
                UPDATE [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
                SET Estado = 'Facturada'
                WHERE ID = @CotID
                  AND Estado IN ('Cotizada', 'Aceptada')
                  AND PrecioCotizado IS NOT NULL;
                IF @@ROWCOUNT <> 1
                    THROW 51036, 'La cotización personalizada ya fue facturada o no está disponible para venta.', 1;
            END

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

-- ----------------------------------------------------------------------------
-- L28: Marca temporal comercial de Nicaragua consistente en anulaciones fiscales y contables
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarAsientoAnulado]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @FechaAnulacion DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @FechaEfectiva DATETIME2 = COALESCE(
        @FechaAnulacion,
        (SELECT TOP 1 Fecha FROM [contabilidad].[AsientosDiario]
         WHERE ReferenciaExterna = CONCAT('REV-', @P3) AND TipoDocumento = N'Reversión'
         ORDER BY ID DESC),
        SWITCHOFFSET(SYSDATETIMEOFFSET(), '-06:00')
    );
    UPDATE [contabilidad].[AsientosDiario] SET
        Estado = 'Anulado',
        AnuladoPor = @P1,
        FechaAnulacion = @FechaEfectiva,
        MotivoAnulacion = @P2
    WHERE ID = @P3 AND Estado IN ('Contabilizado', 'Anulado');
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
    UPDATE [ventas].[Facturas]
    SET EstadoFiscal = 'Anulada',
        AnuladaPor = @P1,
        FechaAnulacion = ISNULL(@P2, SWITCHOFFSET(SYSDATETIMEOFFSET(), '-06:00')),
        MotivoAnulacion = @P3
    WHERE ID = @P4;
END
GO
GO

-- >>> sql_group2_hr_nomina.sql
-- ============================================================================
-- REMEDIACIÓN AUDITORÍA GRUPO 2: RR. HH., Nómina, Pago de Planilla, Vales,
-- Asistencia/Kiosco y Biometría (L04, L05, L12, L17, L19)
-- ============================================================================

SET NOCOUNT ON;
GO

-- 1. L17: Incluir HoraEntrada y HoraSalida en el bloqueo de empleado de Kiosco
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, HoraEntrada, HoraSalida
    FROM [rrhh].[Empleados] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID = @P1 AND EstadoEmpleado = 'Activo';
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo] TO [db_rol_kiosco];
GO

-- 2. L17: Orden determinista en turno laboral por defecto
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerTurnoLaboralActivoDefecto]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos
    FROM [rrhh].[TurnosLaborales]
    WHERE Activo = 1
    ORDER BY ID ASC;
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerTurnoLaboralActivoDefecto] TO [db_rol_kiosco];
GO

-- 3. L19: Huella ligera de descriptores faciales en BD para sincronizar caché multi-worker
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerHuellaDescriptoresFacialesKiosco]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        COUNT(*) AS TotalActivos,
        ISNULL(MAX(ID), 0) AS MaxID,
        ISNULL(CHECKSUM_AGG(BINARY_CHECKSUM(ID, CAST(FaceDescriptor AS VARCHAR(4000)))), 0) AS Huella
    FROM [rrhh].[Empleados]
    WHERE EstadoEmpleado = 'Activo' AND FaceDescriptor IS NOT NULL;
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerHuellaDescriptoresFacialesKiosco] TO [db_rol_kiosco];
GO

-- 4. L12: Vales en nómina filtrados por fecha del período y aplicación parcial sin neto negativo
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSumaValesPendientesUsuario]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0)
    FROM [rrhh].[ValesEmpleados]
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarValesPendientesUsuarioHastaFecha]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Monto, Fecha
    FROM [rrhh].[ValesEmpleados] WITH (UPDLOCK, HOLDLOCK)
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2)
    ORDER BY Fecha ASC, ID ASC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarValeDescontadoPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Descontado = 1
    WHERE ID = @P1 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ActualizarSaldoValeParcialPorID]
    @P1 DECIMAL(10,2) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Monto = @P1, Descontado = 0
    WHERE ID = @P2 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarValesDescontadosUsuario]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Descontado = 1
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2);
END
GO

-- 5. L05: Desembolso verificable de nómina (control de fondos en Caja/Bancos y transición a Pagada)
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoDisponibleCuentaBloqueo]
    @P1 VARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(d.Debe - d.Haber), 0) AS SaldoDisponible
    FROM [contabilidad].[CatalogoCuentas] c WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [contabilidad].[DetalleAsientos] d WITH (UPDLOCK, HOLDLOCK)
        ON d.CuentaID = c.ID
    LEFT JOIN [contabilidad].[AsientosDiario] a WITH (UPDLOCK, HOLDLOCK)
        ON a.ID = d.AsientoID AND a.Estado = 'Contabilizado'
    WHERE c.Codigo = @P1 AND c.Activa = 1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_VerificarAsientoPagoNominaExistente]
    @P1 VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, NumeroComprobante
    FROM [contabilidad].[AsientosDiario] WITH (UPDLOCK, HOLDLOCK)
    WHERE ReferenciaExterna = @P1 AND Estado = 'Contabilizado'
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_MarcarNominaPagada]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[Nomina]
    SET Estado = 'Pagada'
    WHERE ID = @P1 AND Estado = 'Contabilizada';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarNominasContabilizadasPorPeriodoBloqueo]
    @P1 DATE = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID
    FROM [rrhh].[Nomina] WITH (UPDLOCK, HOLDLOCK)
    WHERE PeriodoInicio >= @P1 AND PeriodoFin <= @P2 AND Estado = 'Contabilizada'
    ORDER BY ID ASC;
END
GO
GO

-- >>> sql_group3_accounting_dgi.sql
-- ============================================================================
-- Group 3 Remediation SQL: Accounting, Balance Sheet, DGI Engine/Repo & Forecast
-- Target Database: PanaderiaQA_Prevalidacion_20261015
-- ============================================================================
SET NOCOUNT ON;
GO

-- 1. L24: Saldo disponible con bloqueo UPDLOCK, HOLDLOCK sobre cuentas de efectivo/bancos
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoDisponibleCuenta]
    @CodigoCuenta NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Naturaleza,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber
    FROM [contabilidad].[CatalogoCuentas] C WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [contabilidad].[DetalleAsientos] D WITH (UPDLOCK, HOLDLOCK) ON D.CuentaID = C.ID
    LEFT JOIN [contabilidad].[AsientosDiario] A WITH (UPDLOCK, HOLDLOCK) ON D.AsientoID = A.ID
        AND (
            A.Estado = 'Contabilizado'
            OR (A.Estado = 'Anulado' AND EXISTS (
                SELECT 1
                FROM [contabilidad].[AsientosDiario] R
                WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
                  AND R.Estado = 'Contabilizado'
            ))
        )
    WHERE C.Codigo = @CodigoCuenta
    GROUP BY C.Naturaleza;
END
GO

-- 2. L27: Verificación de conciliación de facturas y compras antes del cierre mensual
CREATE OR ALTER PROCEDURE [contabilidad].[sp_VerificarConciliacionCierrePeriodo]
    @PeriodoID INT,
    @Mes INT,
    @Anio INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @FacturasSinAsiento INT = 0;
    DECLARE @ComprasSinAsiento INT = 0;

    SELECT @FacturasSinAsiento = COUNT(*)
    FROM [ventas].[Facturas] f
    WHERE MONTH(f.FechaHora) = @Mes
      AND YEAR(f.FechaHora) = @Anio
      AND ISNULL(f.EstadoFiscal, 'Emitida') != 'Anulada'
      AND NOT EXISTS (
          SELECT 1
          FROM [contabilidad].[AsientosDiario] a
          WHERE a.Estado = 'Contabilizado'
            AND (
                a.ID = TRY_CONVERT(INT, JSON_VALUE(CASE WHEN ISJSON(f.DocumentoJSON) = 1 THEN f.DocumentoJSON ELSE N'{}' END, '$.asiento_id'))
                OR a.ReferenciaExterna = f.NumeroFactura
                OR a.ReferenciaExterna = CONCAT('FAC-', f.ID)
                OR a.ReferenciaExterna = CAST(f.ID AS NVARCHAR(100))
            )
      );

    SELECT @ComprasSinAsiento = COUNT(*)
    FROM [produccion].[ComprasMateriaPrima] c
    WHERE MONTH(c.Fecha) = @Mes
      AND YEAR(c.Fecha) = @Anio
      AND NOT EXISTS (
          SELECT 1
          FROM [contabilidad].[AsientosDiario] a
          WHERE a.Estado = 'Contabilizado'
            AND (
                a.ReferenciaExterna = CONCAT('COMP-', c.ID)
                OR (c.FacturaProveedor IS NOT NULL AND LTRIM(RTRIM(c.FacturaProveedor)) <> '' AND a.ReferenciaExterna = c.FacturaProveedor)
                OR a.ReferenciaExterna = CAST(c.ID AS NVARCHAR(100))
            )
      );

    SELECT @FacturasSinAsiento AS FacturasSinAsiento, @ComprasSinAsiento AS ComprasSinAsiento;
END
GO

-- 3. L14: Resumen financiero de rango (Utilidad neta contable real vs Flujo de caja operativo)
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerResumenFinancieroRango]
    @FechaInicio DATETIME2,
    @FechaFin DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ISNULL(SUM(CASE WHEN C.Clase = 'Ingreso' OR C.Codigo LIKE '4.%' THEN D.Haber - D.Debe ELSE 0 END), 0) AS IngresosContables,
        ISNULL(SUM(CASE WHEN C.Clase = 'Costo' OR C.Codigo LIKE '5.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS CostosContables,
        ISNULL(SUM(CASE WHEN C.Clase = 'Gasto' OR C.Codigo LIKE '6.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS GastosContables,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                           AND A.Estado = 'Contabilizado' AND ISNULL(A.TipoDocumento, N'') != N'Reversión'
                     THEN D.Debe ELSE 0 END), 0) AS EntradasEfectivo,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                           AND A.Estado = 'Contabilizado' AND ISNULL(A.TipoDocumento, N'') != N'Reversión'
                     THEN D.Haber ELSE 0 END), 0) AS SalidasEfectivo,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                     THEN D.Debe - D.Haber ELSE 0 END), 0) AS FlujoCajaOperativo
    FROM [contabilidad].[DetalleAsientos] D
    JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
    WHERE (
        A.Estado = 'Contabilizado'
        OR (A.Estado = 'Anulado' AND EXISTS (
            SELECT 1
            FROM [contabilidad].[AsientosDiario] R
            WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
              AND R.Estado = 'Contabilizado'
        ))
    )
      AND A.Fecha >= @FechaInicio
      AND A.Fecha < @FechaFin;
END
GO

-- 4. L22: Balance General con separación de Resultados Acumulados Anteriores vs Utilidad del Ejercicio
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceGeneralCorte]
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @InicioEjercicio DATE = DATEFROMPARTS(YEAR(@FechaCorte), 1, 1);
    DECLARE @FinExclusivo DATE = DATEADD(DAY, 1, CAST(@FechaCorte AS DATE));

    WITH SaldosHistoricos AS (
        SELECT
            C.Clase,
            C.Grupo,
            C.Codigo,
            C.Nombre AS Cuenta,
            C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber,
            SUM(CASE WHEN A.Fecha < @InicioEjercicio THEN D.Debe ELSE 0 END) AS DebeAnterior,
            SUM(CASE WHEN A.Fecha < @InicioEjercicio THEN D.Haber ELSE 0 END) AS HaberAnterior,
            SUM(CASE WHEN A.Fecha >= @InicioEjercicio THEN D.Debe ELSE 0 END) AS DebeEjercicio,
            SUM(CASE WHEN A.Fecha >= @InicioEjercicio THEN D.Haber ELSE 0 END) AS HaberEjercicio
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE (
            A.Estado = 'Contabilizado'
            OR (A.Estado = 'Anulado' AND EXISTS (
                SELECT 1
                FROM [contabilidad].[AsientosDiario] R
                WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
                  AND R.Estado = 'Contabilizado'
            ))
        )
          AND A.Fecha < @FinExclusivo
        GROUP BY C.Clase, C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase,
        Grupo,
        Codigo,
        Cuenta,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (TotalDebe - TotalHaber)
            ELSE (TotalHaber - TotalDebe)
        END AS SaldoFinal,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (DebeAnterior - HaberAnterior)
            ELSE (HaberAnterior - DebeAnterior)
        END AS SaldoEjerciciosAnteriores,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (DebeEjercicio - HaberEjercicio)
            ELSE (HaberEjercicio - DebeEjercicio)
        END AS SaldoEjercicioActual
    FROM SaldosHistoricos
    WHERE (TotalDebe - TotalHaber) <> 0
       OR (DebeAnterior - HaberAnterior) <> 0
       OR (DebeEjercicio - HaberEjercicio) <> 0
    ORDER BY Codigo;
END
GO

-- 5. L06 & L07: Snapshot DGI de Ventas Candidatas con asiento_id y reversion_asiento_id
CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIVentasCandidatas]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL,
    @P3 DATETIME2 = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.ID AS id,
        f.NumeroFactura AS numero,
        f.FechaHora AS fecha,
        f.Subtotal AS base,
        f.IVA AS iva,
        f.Total AS total,
        f.EstadoFiscal AS estado,
        f.FechaAnulacion AS anulada_en,
        f.MotivoAnulacion AS motivo_anulacion,
        f.DocumentoJSON AS documento,
        j.AsientoID AS asiento_id,
        a.Fecha AS fecha_asiento,
        r.ID AS reversion_asiento_id,
        r.Fecha AS fecha_reversion
    FROM [ventas].[Facturas] f
    OUTER APPLY (
        SELECT COALESCE(
            TRY_CONVERT(INT, JSON_VALUE(CASE WHEN ISJSON(f.DocumentoJSON) = 1 THEN f.DocumentoJSON ELSE N'{}' END, '$.asiento_id')),
            (SELECT TOP 1 a0.ID FROM [contabilidad].[AsientosDiario] a0 WHERE a0.ReferenciaExterna = f.NumeroFactura ORDER BY a0.ID)
        ) AS AsientoID
    ) j
    LEFT JOIN [contabilidad].[AsientosDiario] a ON a.ID = j.AsientoID
    OUTER APPLY (
        SELECT TOP 1 v.ID, v.Fecha
        FROM [contabilidad].[AsientosDiario] v
        WHERE (
            v.ReferenciaExterna = CONCAT('REV-', j.AsientoID)
            OR v.ReferenciaExterna = CONCAT('REV-', f.NumeroFactura)
            OR v.ReferenciaExterna = CONCAT('REV-FACT-', f.ID)
        )
        ORDER BY v.ID
    ) r
    WHERE (f.FechaHora >= @P1 AND f.FechaHora < @P2)
       OR (f.FechaAnulacion >= @P3 AND f.FechaAnulacion < @P4)
    ORDER BY f.ID;
END
GO

-- 6. L06 & L07: Snapshot DGI de Asientos con tipo_documento
CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIAsientos]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ID AS id,
        NumeroComprobante AS numero,
        Fecha AS fecha,
        Estado AS estado,
        Descripcion AS descripcion,
        ReferenciaExterna AS referencia,
        TipoDocumento AS tipo_documento
    FROM [contabilidad].[AsientosDiario]
    WHERE Fecha >= @P1 AND Fecha < @P2
    ORDER BY ID;
END
GO

-- 7. L11: Historial de Revisiones DGI con Huella para verificación de frescura en GET /admin/dgi
CREATE OR ALTER PROCEDURE [fiscal].[sp_HistorialRevisionesDGIPorPeriodo]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.Huella, r.ResultadoJSON,
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
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.Huella, r.ResultadoJSON,
        r.CreadoEn, r.CreadoPor, r.AprobadoPor, p.Desde, p.Hasta
    FROM [fiscal].[DGI_Revisiones] r
    JOIN [fiscal].[DGI_Periodos] p ON p.ID = r.PeriodoID
    ORDER BY r.ID DESC;
END
GO

-- 8. L25: Histórico de Ventas para Regresión Lineal anclado a la fecha operativa
CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaHistoricoVentasRegresion]
    @FechaHoy DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Corte DATE = ISNULL(@FechaHoy, CONVERT(date, GETDATE()));
    SELECT CONVERT(date, FechaHora) AS Dia, ISNULL(SUM(Total), 0) AS Total
    FROM [ventas].[Facturas]
    WHERE EstadoFiscal = 'Emitida'
      AND CONVERT(date, FechaHora) >= DATEADD(DAY, -29, @Corte)
      AND CONVERT(date, FechaHora) <= @Corte
    GROUP BY CONVERT(date, FechaHora)
    ORDER BY Dia;
END
GO
GO

-- >>> sql_group4_auth_inv_prod.sql
/* ============================================================================
   REMEDIACIÓN AUDITORÍA GRUPO 4 (L08, L09, L10, L16, L18, L20, L21, L23, L26)
   Archivo: scratch/remediation_20261025/sql_group4_auth_inv_prod.sql
   Base de datos objetivo: PanaderiaQA_Prevalidacion_20261015
   ============================================================================ */

SET NOCOUNT ON;
GO

-- ============================================================================
-- 1. AJUSTES DE ESQUEMA IDEMPOTENTES (L10, L18, L20)
-- ============================================================================
IF COL_LENGTH('produccion.Proveedores', 'RUC') IS NULL
BEGIN
    ALTER TABLE [produccion].[Proveedores] ADD [RUC] NVARCHAR(30) NULL;
END
GO

IF COL_LENGTH('produccion.ComprasMateriaPrima', 'IdempotencyKey') IS NULL
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD [IdempotencyKey] NVARCHAR(120) NULL;
END
GO

IF COL_LENGTH('produccion.ComprasMateriaPrima', 'ProveedorRUC') IS NULL
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD [ProveedorRUC] NVARCHAR(30) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'produccion.ComprasMateriaPrima')
      AND name = N'UX_ComprasMateriaPrima_IdempotencyKey'
)
BEGIN
    CREATE UNIQUE INDEX [UX_ComprasMateriaPrima_IdempotencyKey]
    ON [produccion].[ComprasMateriaPrima]([IdempotencyKey])
    WHERE [IdempotencyKey] IS NOT NULL;
END
GO

IF COL_LENGTH('produccion.MateriaPrima', 'CostoUnitario') IS NULL
BEGIN
    ALTER TABLE [produccion].[MateriaPrima] ADD [CostoUnitario] DECIMAL(18, 4) NULL;
END
GO

-- ============================================================================
-- 2. L08: NORMALIZACIÓN DE IDENTIDAD EN BLOQUEO DE LOGIN
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_VerificarBloqueoCuenta]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Ahora DATETIME2 = SYSDATETIME();
    DECLARE @Raw NVARCHAR(100) = LOWER(LTRIM(RTRIM(ISNULL(@Identificador, N'desconocido'))));
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@Raw, N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    DECLARE @Canon NVARCHAR(100) = @Raw;

    IF @Clean LIKE N'[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 8
        SET @Canon = N'+505' + @Clean;
    ELSE IF @Clean LIKE N'505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 11
        SET @Canon = N'+505' + RIGHT(@Clean, 8);
    ELSE IF @Clean LIKE N'00505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 13
        SET @Canon = N'+505' + RIGHT(@Clean, 8);

    SET @DireccionIP = LTRIM(RTRIM(ISNULL(@DireccionIP, '0.0.0.0')));

    SELECT TOP 1
        ID,
        Identificador,
        DireccionIP,
        IntentosFallidos,
        BloqueadoHasta,
        CASE WHEN BloqueadoHasta IS NOT NULL AND BloqueadoHasta > @Ahora THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS EstaBloqueado
    FROM [seguridad].[BloqueosCuenta]
    WHERE Identificador IN (@Canon, @Raw)
      AND DireccionIP = @DireccionIP
      AND BloqueadoHasta > @Ahora
    ORDER BY BloqueadoHasta DESC;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_VerificarBloqueoLogin]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC [seguridad].[sp_VerificarBloqueoCuenta]
        @Identificador = @Identificador,
        @DireccionIP = @DireccionIP;
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
        DECLARE @Raw NVARCHAR(100) = LOWER(LTRIM(RTRIM(ISNULL(@Identificador, N'desconocido'))));
        DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@Raw, N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
        SET @Identificador = @Raw;

        IF @Clean LIKE N'[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 8
            SET @Identificador = N'+505' + @Clean;
        ELSE IF @Clean LIKE N'505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 11
            SET @Identificador = N'+505' + RIGHT(@Clean, 8);
        ELSE IF @Clean LIKE N'00505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 13
            SET @Identificador = N'+505' + RIGHT(@Clean, 8);

        SET @DireccionIP = LTRIM(RTRIM(ISNULL(@DireccionIP, '0.0.0.0')));

        SELECT @MaxIntentos = ISNULL(TRY_CAST(Valor AS INT), @MaxIntentos)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_intentos_max';

        SELECT @MinutosBloqueo = ISNULL(TRY_CAST(Valor AS INT), @MinutosBloqueo)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_minutos';

        IF @Exitoso = 1
        BEGIN
            DELETE FROM [seguridad].[BloqueosCuenta]
            WHERE Identificador IN (@Identificador, @Raw) AND DireccionIP = @DireccionIP;

            SELECT
                CAST(0 AS BIT) AS Bloqueado,
                CAST(0 AS BIT) AS RecienBloqueado,
                0 AS IntentosFallidos,
                CAST(NULL AS DATETIME2) AS BloqueadoHasta;
            RETURN;
        END

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

-- ============================================================================
-- 3. L09: CONTEO ACUMULADO DE FALLOS TOTP POR CUENTA EN VENTANA DE TIEMPO
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerFallosTOTPRecientes]
    @Subject NVARCHAR(128),
    @MinExpiresAt BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Attempts), 0) AS TotalFallos
    FROM [seguridad].[AuthChallenges] WITH (UPDLOCK, HOLDLOCK)
    WHERE Subject = @Subject
      AND Kind LIKE 'totp%'
      AND Verified = 0
      AND ExpiresAt > @MinExpiresAt;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_LimpiarFallosTOTPUsuario]
    @Subject NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [seguridad].[AuthChallenges]
    SET Verified = 1,
        Consumed = 1,
        Attempts = 0
    WHERE Subject = @Subject
      AND Kind LIKE 'totp%';
END
GO

-- ============================================================================
-- 4. L23: INVARIANTE DE ÚLTIMO SUPERADMIN ACTIVO BAJO BLOQUEO SERIALIZABLE
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_ContarSuperAdminsActivosBloqueo]
    @TargetUserID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @SuperAdminRolID INT;
    SELECT @SuperAdminRolID = ID
    FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
    WHERE Nombre = 'SuperAdmin';

    DECLARE @TargetRolID INT, @TargetActivo BIT, @TargetRolNombre NVARCHAR(50);
    SELECT @TargetRolID = u.RolID, @TargetActivo = u.Activo, @TargetRolNombre = r.Nombre
    FROM [seguridad].[Usuarios] u WITH (UPDLOCK, HOLDLOCK)
    JOIN [seguridad].[Roles] r ON r.ID = u.RolID
    WHERE u.ID = @TargetUserID;

    DECLARE @Restantes INT = 0;
    SELECT @Restantes = COUNT(*)
    FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
    WHERE RolID = @SuperAdminRolID
      AND Activo = 1
      AND ID <> ISNULL(@TargetUserID, -1);

    SELECT
        @TargetRolID AS TargetRolID,
        @TargetRolNombre AS TargetRolNombre,
        @TargetActivo AS TargetActivo,
        @SuperAdminRolID AS SuperAdminRolID,
        ISNULL(@Restantes, 0) AS SuperAdminsActivosRestantes;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarRolUsuario]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P1;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @P2 <> @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @P1;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET RolID = @P2
        WHERE ID = @P1;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ActualizarRolUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarUsuario]
    @UsuarioID INT,
    @NombreCompleto NVARCHAR(100) = NULL,
    @RolID INT = NULL,
    @Activo BIT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        DECLARE @NuevoRolID INT = ISNULL(@RolID, @RolActualID);
        DECLARE @NuevoActivo BIT = ISNULL(@Activo, @ActivoActual);

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
           AND (@NuevoRolID <> @SuperAdminRolID OR @NuevoActivo = 0)
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET NombreCompleto = ISNULL(@NombreCompleto, NombreCompleto),
            RolID = @NuevoRolID,
            Activo = @NuevoActivo
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ActualizarUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ToggleActivoUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P1;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @P1;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 1 ^ Activo
        WHERE ID = @P1;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ToggleActivoUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_CambiarEstadoUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 1 ^ Activo
        OUTPUT DELETED.NombreCompleto, DELETED.Username, DELETED.RolID, DELETED.Activo AS ActivoAntes, INSERTED.Activo AS ActivoDespues
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_CambiarEstadoUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_EliminarUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 0
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_EliminarUsuario';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 5. L26: ALERTAS SMTP OUTBOX CON DESTINATARIO INDIVIDUAL PERSISTIDO
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_EncolarAlertaSMTP]
    @ErrorID BIGINT,
    @DestinatariosJSON NVARCHAR(MAX) = NULL,
    @Forzar BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @LockResult INT;
        EXEC @LockResult = sys.sp_getapplock @Resource = N'panaderia.smtp.outbox.v1',
             @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;

        INSERT INTO [seguridad].[AlertasSMTPOutbox](ErrorID, DedupKey, DestinatariosJSON, Forzar)
        SELECT b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError, 120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)), @DestinatariosJSON, @Forzar
        FROM [seguridad].[BitacoraErrores] b
        WHERE b.ID = @ErrorID AND b.NotificadoSMTP = 0
          AND NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] o WHERE o.ErrorID = b.ID);

        UPDATE [seguridad].[AlertasSMTPOutbox]
        SET DestinatariosJSON = COALESCE(@DestinatariosJSON, DestinatariosJSON),
            Forzar = CASE WHEN @Forzar = 1 THEN 1 ELSE Forzar END
        WHERE ErrorID = @ErrorID AND Estado <> 'Sent';

        COMMIT;
        SELECT CAST(CASE WHEN EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] WHERE ErrorID = @ErrorID)
                        THEN 1 ELSE 0 END AS BIT) AS Encolada;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ReclamarAlertaSMTP]
    @ErrorID BIGINT = NULL,
    @VentanaSegundos INT = 300,
    @LeaseSegundos INT = 300,
    @SembrarLote INT = 20
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @SembrarLote NOT BETWEEN 0 AND 100 OR @VentanaSegundos NOT BETWEEN 0 AND 86400
       OR @LeaseSegundos NOT BETWEEN 60 AND 3600
        THROW 51071, 'Limites SMTP invalidos.', 1;
    DECLARE @Ahora DATETIME2(3) = SYSUTCDATETIME(), @Elegido BIGINT, @Clave BINARY(32),
            @Token UNIQUEIDENTIFIER = NEWID(), @LockResult INT;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC @LockResult = sys.sp_getapplock @Resource = N'panaderia.smtp.outbox.v1',
             @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;

        INSERT INTO [seguridad].[AlertasSMTPOutbox](ErrorID, DedupKey)
        SELECT TOP (@SembrarLote) b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError, 120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER))
        FROM [seguridad].[BitacoraErrores] b
        WHERE b.NotificadoSMTP = 0
          AND NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] o WHERE o.ErrorID = b.ID)
        ORDER BY b.ID;

        UPDATE TOP (100) o SET Estado = 'Suppressed', ClaimToken = NULL, LeaseHasta = NULL
        FROM [seguridad].[AlertasSMTPOutbox] o
        JOIN [seguridad].[AlertasSMTPDedup] d ON d.DedupKey = o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.Forzar = 0
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta <= @Ahora)
          AND d.UltimoEnvio > DATEADD(SECOND, -@VentanaSegundos, @Ahora)
          AND (@ErrorID IS NULL OR o.ErrorID = @ErrorID);

        SELECT TOP(1) @Elegido = o.ErrorID, @Clave = o.DedupKey
        FROM [seguridad].[AlertasSMTPOutbox] o
        LEFT JOIN [seguridad].[AlertasSMTPDedup] d ON d.DedupKey = o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.DisponibleDesde <= @Ahora
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta <= @Ahora)
          AND (d.LeaseHasta IS NULL OR d.LeaseHasta <= @Ahora)
          AND (o.Forzar = 1 OR d.UltimoEnvio IS NULL OR d.UltimoEnvio <= DATEADD(SECOND, -@VentanaSegundos, @Ahora))
          AND (@ErrorID IS NULL OR o.ErrorID = @ErrorID)
        ORDER BY CASE WHEN o.DestinatariosJSON IS NOT NULL THEN 0 ELSE 1 END,
                 o.Forzar DESC,
                 o.DisponibleDesde,
                 o.ErrorID;

        IF @Elegido IS NOT NULL
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPDedup] WHERE DedupKey = @Clave)
                INSERT INTO [seguridad].[AlertasSMTPDedup](DedupKey) VALUES(@Clave);
            UPDATE [seguridad].[AlertasSMTPDedup]
               SET ClaimToken = @Token, LeaseHasta = DATEADD(SECOND, @LeaseSegundos, @Ahora)
             WHERE DedupKey = @Clave;
            UPDATE [seguridad].[AlertasSMTPOutbox] SET Estado = 'Sending', ClaimToken = @Token,
                   LeaseHasta = DATEADD(SECOND, @LeaseSegundos, @Ahora), Intentos = Intentos + 1
             WHERE ErrorID = @Elegido;
        END;
        COMMIT;
        SELECT b.*, o.ClaimToken, o.DestinatariosJSON, o.DestinatariosJSON AS Destinatario
        FROM [seguridad].[AlertasSMTPOutbox] o
        JOIN [seguridad].[BitacoraErrores] b ON b.ID = o.ErrorID
        WHERE o.ErrorID = @Elegido AND o.ClaimToken = @Token;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 6. L16: CLIENTES - NORMALIZACIÓN Y UNICIDAD DE TELÉFONO BAJO BLOQUEO
-- ============================================================================
CREATE OR ALTER PROCEDURE [crm].[sp_VerificarTelefonoClienteDuplicado]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P1, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    SELECT ID
    FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID <> ISNULL(@P2, 0)
      AND ID > 1
      AND Telefono IS NOT NULL
      AND LTRIM(RTRIM(Telefono)) <> ''
      AND (
          CASE
              WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                   AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
              THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
              WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 13
                   AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 5) = '00505'
              THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
              ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
          END = @Clean
      );
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
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P3, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID <> ISNULL(@P7, 0)
          AND ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 13
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 5) = '00505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    SET NOCOUNT OFF;
    UPDATE [crm].[Clientes]
    SET Nombre = @P1,
        Apellidos = @P2,
        Telefono = @Clean,
        Genero = @P4,
        FechaNacimiento = @P5,
        NivelConfianzaID = @P6
    WHERE ID = @P7 AND ID > 1;
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
        DECLARE @Clean VARCHAR(30) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '');
        IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = '505'
            SET @Clean = RIGHT(@Clean, 8);
        ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = '00505'
            SET @Clean = RIGHT(@Clean, 8);

        IF EXISTS (
            SELECT 1
            FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
            WHERE ID <> @ClienteID
              AND ID > 1
              AND Telefono IS NOT NULL
              AND (
                  CASE
                      WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                           AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                      THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                      ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
                  END = @Clean
              )
        )
            THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

        IF NOT EXISTS (SELECT 1 FROM [crm].[NivelesConfianza] WHERE ID = @NivelConfianzaID)
            THROW 52021, 'Nivel de fidelidad inexistente.', 1;

        UPDATE [crm].[Clientes]
        SET Nombre = @Nombre,
            Apellidos = @Apellidos,
            Telefono = @Clean,
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
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P3, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    INSERT INTO [crm].[Clientes] (
        Nombre, Apellidos, Telefono, PasswordHash, Genero,
        FechaNacimiento, RutaFotoPerfil, EsInvitado, NivelConfianzaID
    )
    VALUES (@P1, @P2, @Clean, @P4, @P5, @P6, @P7, 0, 1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_InsertarClienteRapido]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P2, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF @Clean <> N'' AND EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    INSERT INTO [crm].[Clientes](Nombre, Telefono, NivelConfianzaID)
    OUTPUT INSERTED.ID
    VALUES(@P1, CASE WHEN @Clean <> N'' THEN @Clean ELSE @P2 END, 1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerClientePorTelefono]
    @Telefono VARCHAR(30)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean VARCHAR(30) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = '505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = '00505'
        SET @Clean = RIGHT(@Clean, 8);

    SELECT ID, Nombre, Apellidos, Telefono, PasswordHash, EsInvitado, NivelConfianzaID, FechaNacimiento, RutaFotoPerfil
    FROM [crm].[Clientes]
    WHERE Telefono = @Telefono
       OR (
           @Clean <> '' AND Telefono IS NOT NULL AND
           CASE
               WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                    AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
               THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
               ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
           END = @Clean
       )
    ORDER BY EsInvitado ASC, ID DESC;
END
GO

-- ============================================================================
-- 7. L10 y L18: COMPRAS IDEMPOTENTES Y SOPORTE RUC DE PROVEEDOR PARA IVA
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_CrearProveedor]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [produccion].[Proveedores] (Nombre, Telefono, RUC)
    OUTPUT INSERTED.ID
    VALUES (@P1, @P2, @P3);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarProveedorActivo]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE [produccion].[Proveedores]
    SET Nombre = @P1,
        Telefono = @P2,
        RUC = COALESCE(@P4, RUC)
    WHERE ID = @P3 AND Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_VerificarProveedorActivo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, RUC FROM [produccion].[Proveedores] WHERE ID = @P1 AND Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarProveedoresActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Telefono, RUC
    FROM [produccion].[Proveedores]
    WHERE Activo = 1
    ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerCompraPorIdempotencia]
    @IdempotencyKey NVARCHAR(120),
    @ProveedorID INT = NULL,
    @FacturaProveedor NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1
        ID,
        MateriaPrimaID,
        ProveedorID,
        Cantidad,
        CostoTotal,
        FacturaProveedor,
        IVADocumentado,
        Fecha,
        IdempotencyKey
    FROM [produccion].[ComprasMateriaPrima] WITH (UPDLOCK, HOLDLOCK)
    WHERE IdempotencyKey = @IdempotencyKey
       OR (
           @ProveedorID IS NOT NULL
           AND @FacturaProveedor IS NOT NULL
           AND ProveedorID = @ProveedorID
           AND UPPER(LTRIM(RTRIM(FacturaProveedor))) = UPPER(LTRIM(RTRIM(@FacturaProveedor)))
       )
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarCompraMateriaPrima]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DATETIME2 = NULL,
    @P8 NVARCHAR(120) = NULL,
    @P9 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @P8 IS NOT NULL
    BEGIN
        DECLARE @ExistingID INT;
        SELECT TOP 1 @ExistingID = ID
        FROM [produccion].[ComprasMateriaPrima] WITH (UPDLOCK, HOLDLOCK)
        WHERE IdempotencyKey = @P8;

        IF @ExistingID IS NOT NULL
        BEGIN
            SELECT @ExistingID AS ID, CAST(1 AS BIT) AS YaExistia;
            RETURN;
        END
    END

    INSERT INTO [produccion].[ComprasMateriaPrima] (
        MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha, IdempotencyKey, ProveedorRUC
    )
    OUTPUT INSERTED.ID, CAST(0 AS BIT) AS YaExistia
    VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, @P8, @P9);
END
GO

-- ============================================================================
-- 8. L20: INVENTARIO / RECETAS - CAMBIO DE UNIDAD DE MEDIDA CON CONVERSIÓN
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerEstadoMateriaPrimaParaEdicion]
    @MateriaID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        m.ID,
        m.Nombre,
        m.UnidadMedidaID,
        m.StockActual,
        m.StockMinimo,
        m.CostoUnitario,
        (SELECT COUNT(*) FROM [produccion].[RecetaProducto] WHERE MateriaPrimaID = m.ID) AS TotalRecetas,
        (SELECT COUNT(*) FROM [produccion].[ComprasMateriaPrima] WHERE MateriaPrimaID = m.ID) AS TotalCompras,
        (SELECT COUNT(*) FROM [produccion].[ConsumoLote] WHERE MateriaPrimaID = m.ID) AS TotalConsumos
    FROM [produccion].[MateriaPrima] m WITH (UPDLOCK, HOLDLOCK)
    WHERE m.ID = @MateriaID;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarMateriaPrima]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 INT = NULL,
    @FactorConversion DECIMAL(18, 6) = NULL,
    @UsuarioID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @UnidadActualID INT,
                @StockActual DECIMAL(18, 2),
                @StockMinimoActual DECIMAL(18, 2),
                @CostoUnitarioActual DECIMAL(18, 4);

        SELECT
            @UnidadActualID = UnidadMedidaID,
            @StockActual = StockActual,
            @StockMinimoActual = StockMinimo,
            @CostoUnitarioActual = CostoUnitario
        FROM [produccion].[MateriaPrima] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P4;

        IF @UnidadActualID IS NULL
        BEGIN
            IF @OwnTran = 1 COMMIT TRANSACTION;
            SET NOCOUNT OFF;
            UPDATE [produccion].[MateriaPrima] SET Nombre = @P1 WHERE ID = @P4 AND 1 = 0;
            RETURN;
        END

        IF @P2 <> @UnidadActualID
        BEGIN
            DECLARE @TieneUso BIT = 0;
            IF @StockActual > 0
               OR EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE MateriaPrimaID = @P4)
               OR EXISTS (SELECT 1 FROM [produccion].[ComprasMateriaPrima] WHERE MateriaPrimaID = @P4)
               OR EXISTS (SELECT 1 FROM [produccion].[ConsumoLote] WHERE MateriaPrimaID = @P4)
            BEGIN
                SET @TieneUso = 1;
            END

            IF @FactorConversion IS NOT NULL AND @FactorConversion <= 0
                THROW 52040, 'El factor de conversión debe ser mayor a cero.', 1;

            IF @TieneUso = 1 AND (@FactorConversion IS NULL OR @FactorConversion <= 0)
                THROW 52040, 'No se puede cambiar la unidad de medida de una materia prima con stock, recetas o historial sin proporcionar un factor de conversión válido.', 1;

            IF @FactorConversion IS NOT NULL AND @FactorConversion > 0
            BEGIN
                DECLARE @NuevoStock DECIMAL(18, 2) = ROUND(@StockActual * @FactorConversion, 2);
                DECLARE @NuevoMinimo DECIMAL(18, 2) = CASE
                    WHEN @P3 IS NOT NULL AND @P3 <> @StockMinimoActual THEN @P3
                    ELSE ROUND(@StockMinimoActual * @FactorConversion, 2)
                END;
                DECLARE @NuevoCosto DECIMAL(18, 4) = CASE
                    WHEN @CostoUnitarioActual IS NOT NULL THEN ROUND(@CostoUnitarioActual / @FactorConversion, 4)
                    ELSE NULL
                END;

                UPDATE [produccion].[RecetaProducto]
                SET CantidadNecesaria = CASE
                    WHEN ROUND(CantidadNecesaria * @FactorConversion, 2) < 0.01 THEN 0.01
                    ELSE ROUND(CantidadNecesaria * @FactorConversion, 2)
                END
                WHERE MateriaPrimaID = @P4;

                DECLARE @ActorID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
                DECLARE @IP VARCHAR(45) = TRY_CAST(SESSION_CONTEXT(N'ip') AS VARCHAR(45));
                DECLARE @AntesJSON NVARCHAR(MAX) = CONCAT(
                    N'{"unidad_id":', @UnidadActualID,
                    N',"stock_actual":', @StockActual,
                    N',"stock_minimo":', @StockMinimoActual, N'}'
                );
                DECLARE @DespuesJSON NVARCHAR(MAX) = CONCAT(
                    N'{"unidad_id":', @P2,
                    N',"factor_conversion":', @FactorConversion,
                    N',"stock_actual":', @NuevoStock,
                    N',"stock_minimo":', @NuevoMinimo, N'}'
                );

                EXEC [seguridad].[sp_RegistrarAuditoria]
                    @UsuarioID = @ActorID,
                    @Accion = 'CONVERTIR_UNIDAD_MP',
                    @Entidad = 'MateriaPrima',
                    @EntidadID = @P4,
                    @DatosAntes = @AntesJSON,
                    @DatosDespues = @DespuesJSON,
                    @IP = @IP;

                SET NOCOUNT OFF;
                UPDATE [produccion].[MateriaPrima]
                SET Nombre = @P1,
                    UnidadMedidaID = @P2,
                    StockActual = @NuevoStock,
                    StockMinimo = @NuevoMinimo,
                    CostoUnitario = @NuevoCosto
                WHERE ID = @P4;

                IF @OwnTran = 1 COMMIT TRANSACTION;
                RETURN;
            END
        END

        SET NOCOUNT OFF;
        UPDATE [produccion].[MateriaPrima]
        SET Nombre = @P1,
            UnidadMedidaID = @P2,
            StockMinimo = @P3
        WHERE ID = @P4;

        IF @OwnTran = 1 COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_ActualizarMateriaPrima';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 9. L21: PRODUCCIÓN - VALIDACIÓN DE PRODUCTO ACTIVO Y NO BEBIDA EN LOTES
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_ValidarProductoParaProduccion]
    @ProductoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.ID,
        p.Nombre,
        p.Activo,
        ISNULL(p.EsFicticio, 0) AS EsFicticio,
        p.CategoriaID,
        ISNULL(c.Nombre, '') AS CategoriaNombre,
        (SELECT COUNT(*) FROM [produccion].[RecetaProducto] r WHERE r.ProductoID = p.ID AND r.CantidadNecesaria > 0) AS TieneReceta
    FROM [catalogo].[Productos] p WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
    WHERE p.ID = @ProductoID;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarLoteProduccion]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Activo BIT, @EsFicticio BIT, @Categoria NVARCHAR(100);
    SELECT
        @Activo = p.Activo,
        @EsFicticio = ISNULL(p.EsFicticio, 0),
        @Categoria = ISNULL(c.Nombre, N'')
    FROM [catalogo].[Productos] p
    LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
    WHERE p.ID = @P1;

    IF @Activo IS NULL
        THROW 52034, 'El producto especificado no existe.', 1;
    IF @Activo = 0
        THROW 52035, 'No se puede registrar un lote de producción para un producto inactivo.', 1;
    IF LOWER(LTRIM(RTRIM(@Categoria))) IN (N'bebidas', N'bebida', N'reventa') OR @EsFicticio = 1
        THROW 52036, 'No se puede registrar un lote de producción para productos de la categoría Bebidas o no producibles.', 1;

    INSERT INTO [produccion].[ProduccionLotes] (ProductoID, CantidadProducida)
    OUTPUT INSERTED.ID
    VALUES (@P1, @P2);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_RegistrarLoteProduccion]
    @ProductoID INT,
    @CantidadProducida INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        IF @CantidadProducida <= 0
            THROW 52031, 'La cantidad a producir debe ser un entero positivo.', 1;

        DECLARE @Activo BIT, @EsFicticio BIT, @Categoria NVARCHAR(100);
        SELECT
            @Activo = p.Activo,
            @EsFicticio = ISNULL(p.EsFicticio, 0),
            @Categoria = ISNULL(c.Nombre, N'')
        FROM [catalogo].[Productos] p
        LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
        WHERE p.ID = @ProductoID;

        IF @Activo IS NULL
            THROW 52034, 'El producto especificado no existe.', 1;
        IF @Activo = 0
            THROW 52035, 'No se puede registrar un lote de producción para un producto inactivo.', 1;
        IF LOWER(LTRIM(RTRIM(@Categoria))) IN (N'bebidas', N'bebida', N'reventa') OR @EsFicticio = 1
            THROW 52036, 'No se puede registrar un lote de producción para productos de la categoría Bebidas o no producibles.', 1;

        IF NOT EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE ProductoID = @ProductoID AND CantidadNecesaria > 0)
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

        IF @OwnTran = 1
            COMMIT TRANSACTION;

        SELECT @LoteID AS LoteID;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_RegistrarLoteProduccion';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 10. PERMISOS PARA ROLES DE BASE DE DATOS EN PROCEDIMIENTOS NUEVOS/ACTUALIZADOS
-- ============================================================================
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionGlobal] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[fiscal].[sp_RegistrarBitacoraFiscal] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_RegistrarEventoFiscalOperacion] TO [db_rol_produccion];
GO
GO

-- ============================================================================
-- REMEDIACI?N AUDITOR?A DE REGLAS DE NEGOCIO (2026-10-25: L01-L28)
-- ============================================================================
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- >>> sql_group1_pos_kds_fiscal.sql
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
-- ============================================================================
-- REMEDIACIÓN GRUPO 1: POS, Arqueos, Encargos/KDS, Cotizaciones y Anulaciones Fiscales
-- Hallazgos: L01, L02, L03, L13, L15, L28
-- ============================================================================

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET NOCOUNT ON;
GO

-- ----------------------------------------------------------------------------
-- L13: Cálculo consistente del efectivo esperado de la gaveta del turno POS
-- Distingue la gaveta operativa del turno POS (ventas.Pagos por TurnoReceptorID,
-- incluyendo cobros en efectivo y restando devoluciones/anulaciones del turno)
-- respecto de Caja General de oficina (EgresosPrivados / ValesEmpleados).
-- ----------------------------------------------------------------------------
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
    FROM [ventas].[Pagos] p
    WHERE p.TurnoReceptorID = @P1;
END
GO

CREATE OR ALTER PROCEDURE [ventas].[sp_ObtenerResumenTurnoCaja]
    @TurnoID INT
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM [ventas].[Pagos] p JOIN [ventas].[Facturas] f ON f.ID=p.FacturaID
               JOIN [ventas].[TurnosCaja] t ON t.ID=@TurnoID
               WHERE p.Monto<>0 AND (p.TurnoReceptorID IS NULL OR p.UsuarioReceptorID IS NULL)
                 AND (f.TurnoID=@TurnoID OR (p.FechaPago>=t.FechaApertura AND (t.FechaCierre IS NULL OR p.FechaPago<=t.FechaCierre))))
        THROW 51021, 'Existen movimientos históricos sin receptor de caja. Conciliar antes del arqueo.', 1;

    SELECT
        ISNULL(SUM(CASE WHEN (p.MetodoPago = 'Efectivo' OR (p.MetodoPago='Efectivo USD' AND p.MonedaRegistro='NIO')) THEN p.Monto ELSE 0 END), 0) AS EfectivoCordobasSistema,
        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' AND p.MonedaRegistro<>'NIO' THEN p.Monto ELSE 0 END), 0) AS EfectivoUSDSistema,
        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TransferenciasSistema
    FROM [ventas].[Pagos] p
    WHERE p.TurnoReceptorID = @TurnoID;
END
GO

IF DATABASE_PRINCIPAL_ID('db_rol_cajero_pos') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_cajero_pos];
IF DATABASE_PRINCIPAL_ID('db_rol_gerencia') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_gerencia];
IF DATABASE_PRINCIPAL_ID('db_rol_superadmin') IS NOT NULL
    GRANT EXECUTE ON OBJECT::[ventas].[sp_ObtenerResumenTurnoCaja] TO [db_rol_superadmin];
GO

-- ----------------------------------------------------------------------------
-- L03: Máquina de estados estricta para encargos en KDS y bloqueo de pago duplicado
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarEstadoEncargoCompare]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    DECLARE @FacturaID INT;
    SELECT @FacturaID = ID FROM [ventas].[Facturas] WITH(UPDLOCK, HOLDLOCK)
      WHERE CodigoSeguimiento = @P2 AND EstadoFiscal = 'Emitida';

    IF @FacturaID IS NOT NULL
    BEGIN
        DECLARE @EstadoActual NVARCHAR(50);
        SELECT @EstadoActual = Estado FROM [ventas].[Encargos] WITH(UPDLOCK, HOLDLOCK)
          WHERE FacturaID = @FacturaID;

        DECLARE @EstadoDestino NVARCHAR(50) = CASE WHEN @P1 = N'En Preparacion' THEN N'En Proceso' ELSE @P1 END;
        DECLARE @EstadoEsperado NVARCHAR(50) = CASE WHEN @P3 = N'En Preparacion' THEN N'En Proceso' ELSE @P3 END;

        IF (@EstadoActual = N'Entregado' OR @EstadoEsperado = N'Entregado') AND @EstadoDestino <> N'Entregado'
            THROW 51034, 'Un encargo ya entregado es estado terminal en KDS y no puede revertirse ni cancelarse.', 1;

        IF @EstadoActual IN (N'Cancelado', N'Anulada') OR @EstadoEsperado IN (N'Cancelado', N'Anulada')
            THROW 51034, 'Un encargo cancelado o anulado no admite transiciones.', 1;

        IF NOT (
            (@EstadoEsperado = N'Pendiente' AND @EstadoDestino IN (N'En Proceso', N'Listo', N'Entregado'))
            OR (@EstadoEsperado = N'En Proceso' AND @EstadoDestino IN (N'Listo', N'Entregado'))
            OR (@EstadoEsperado = N'Listo' AND @EstadoDestino IN (N'Entregado'))
            OR (@EstadoEsperado = @EstadoDestino AND @EstadoDestino IN (N'Pendiente', N'En Proceso', N'Listo', N'Entregado'))
        )
            THROW 51034, 'Transición de estado de encargo inválida o regresiva.', 1;

        IF @EstadoDestino = N'Entregado' AND IS_MEMBER('db_rol_produccion') = 1 AND EXISTS (
            SELECT 1 FROM [ventas].[Facturas] f WHERE f.ID = @FacturaID AND
              f.Total > ISNULL((SELECT SUM(p.Monto) FROM [ventas].[Pagos] p WHERE p.FacturaID = f.ID), 0))
            THROW 51032, 'El cobro pendiente debe confirmarlo un cajero con turno abierto.', 1;

        UPDATE e SET Estado = @EstadoDestino
        FROM [ventas].[Encargos] AS e
        JOIN [ventas].[Facturas] AS f ON e.FacturaID = f.ID
        WHERE f.ID = @FacturaID AND f.EstadoFiscal = 'Emitida' AND e.Estado = @EstadoEsperado;
    END
    ELSE
    BEGIN
        UPDATE e SET Estado = @P1
        FROM [ventas].[Encargos] AS e
        JOIN [ventas].[Facturas] AS f ON e.FacturaID = f.ID
        WHERE f.ID = @FacturaID AND f.EstadoFiscal = 'Emitida' AND e.Estado = @P3;
    END
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
    SET @UsuarioReceptorID = COALESCE(@UsuarioReceptorID, TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT));
    DECLARE @TotalFactura DECIMAL(18, 2);
    SELECT @TotalFactura = Total FROM [ventas].[Facturas] WITH(UPDLOCK, HOLDLOCK) WHERE ID = @P1 AND EstadoFiscal = 'Emitida';
    IF @TotalFactura IS NULL
        THROW 51025, 'La factura no está emitida.', 1;

    DECLARE @PagadoActual DECIMAL(18, 2);
    SELECT @PagadoActual = ISNULL(SUM(Monto), 0) FROM [ventas].[Pagos] WITH(UPDLOCK, HOLDLOCK) WHERE FacturaID = @P1;
    IF @P3 IS NULL OR @P3 <= 0 OR (@PagadoActual + @P3) > @TotalFactura
        THROW 51035, 'El encargo ya fue pagado o el monto excede el saldo pendiente.', 1;

    IF @TurnoReceptorID IS NULL
        SELECT TOP 1 @TurnoReceptorID = ID FROM [ventas].[TurnosCaja] WITH(UPDLOCK, HOLDLOCK)
        WHERE UsuarioID = @UsuarioReceptorID AND Cerrado = 0 ORDER BY ID DESC;
    IF NOT EXISTS (SELECT 1 FROM [ventas].[TurnosCaja] WITH(UPDLOCK, HOLDLOCK) WHERE ID = @TurnoReceptorID AND UsuarioID = @UsuarioReceptorID AND Cerrado = 0)
        THROW 51026, 'El saldo requiere la caja abierta del usuario receptor.', 1;
    IF EXISTS (SELECT 1 FROM [ventas].[ArqueoCaja] WHERE TurnoID = @TurnoReceptorID AND EstadoArqueo IN ('Pendiente', 'Verificado'))
        THROW 51027, 'La caja receptora tiene un arqueo pendiente.', 1;

    INSERT INTO [ventas].[Pagos] (FacturaID, MetodoPago, Monto, NombreTransferente, FechaPago, MonedaRegistro, TipoCambioAplicado, TurnoReceptorID, UsuarioReceptorID)
    VALUES (@P1, @P2, @P3, @P4, @P5, 'NIO', @P6, @TurnoReceptorID, @UsuarioReceptorID);
END
GO

-- ----------------------------------------------------------------------------
-- L15: Vínculo único de cotización a factura (uso único con bloqueo transaccional)
-- ----------------------------------------------------------------------------
IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = 'CK_Cotizaciones_Estado'
      AND parent_object_id = OBJECT_ID('crm.Cotizaciones')
)
BEGIN
    ALTER TABLE [crm].[Cotizaciones] DROP CONSTRAINT [CK_Cotizaciones_Estado];
END
GO

ALTER TABLE [crm].[Cotizaciones] WITH CHECK ADD CONSTRAINT [CK_Cotizaciones_Estado]
    CHECK ([Estado] IN ('Pendiente', 'Cotizada', 'Aceptada', 'Facturada', 'Rechazada'));
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerCotizacionParaCalculoVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Especificaciones, PrecioCotizado
    FROM [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID = @P1
      AND Estado IN ('Cotizada', 'Aceptada')
      AND PrecioCotizado IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM [ventas].[Facturas] f WITH (UPDLOCK, HOLDLOCK)
          WHERE f.EstadoFiscal = 'Emitida'
            AND f.DocumentoJSON IS NOT NULL
            AND ISJSON(f.DocumentoJSON) = 1
            AND EXISTS (
                SELECT 1
                FROM OPENJSON(f.DocumentoJSON, '$.productos')
                WHERE TRY_CAST(JSON_VALUE([value], '$.cotizacion_id') AS INT) = @P1
            )
      );
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_MarcarCotizacionAceptadaEnVenta]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
    SET Estado = 'Facturada'
    WHERE ID = @P1
      AND Estado IN ('Cotizada', 'Aceptada')
      AND PrecioCotizado IS NOT NULL;
    IF @@ROWCOUNT <> 1
        THROW 51036, 'La cotización personalizada ya fue facturada o no está disponible para venta.', 1;
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

        IF EXISTS (SELECT 1 FROM [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK) WHERE ID = @CotizacionID AND Estado = 'Facturada')
            THROW 52028, 'La cotización ya fue facturada y no puede reutilizarse ni cambiar de estado.', 1;

        UPDATE [crm].[Cotizaciones]
        SET Estado = @NuevoEstado,
            PrecioCotizado = ISNULL(@PrecioCotizado, PrecioCotizado)
        WHERE ID = @CotizacionID
          AND Estado <> 'Facturada';
    END TRY
    BEGIN CATCH
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'crm.sp_ActualizarEstadoCotizacion';
        THROW;
    END CATCH
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

            IF @CotID IS NOT NULL
            BEGIN
                UPDATE [crm].[Cotizaciones] WITH (UPDLOCK, HOLDLOCK)
                SET Estado = 'Facturada'
                WHERE ID = @CotID
                  AND Estado IN ('Cotizada', 'Aceptada')
                  AND PrecioCotizado IS NOT NULL;
                IF @@ROWCOUNT <> 1
                    THROW 51036, 'La cotización personalizada ya fue facturada o no está disponible para venta.', 1;
            END

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

-- ----------------------------------------------------------------------------
-- L28: Marca temporal comercial de Nicaragua consistente en anulaciones fiscales y contables
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarAsientoAnulado]
    @P1 INT = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @FechaAnulacion DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @FechaEfectiva DATETIME2 = COALESCE(
        @FechaAnulacion,
        (SELECT TOP 1 Fecha FROM [contabilidad].[AsientosDiario]
         WHERE ReferenciaExterna = CONCAT('REV-', @P3) AND TipoDocumento = N'Reversión'
         ORDER BY ID DESC),
        SWITCHOFFSET(SYSDATETIMEOFFSET(), '-06:00')
    );
    UPDATE [contabilidad].[AsientosDiario] SET
        Estado = 'Anulado',
        AnuladoPor = @P1,
        FechaAnulacion = @FechaEfectiva,
        MotivoAnulacion = @P2
    WHERE ID = @P3 AND Estado IN ('Contabilizado', 'Anulado');
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
    UPDATE [ventas].[Facturas]
    SET EstadoFiscal = 'Anulada',
        AnuladaPor = @P1,
        FechaAnulacion = ISNULL(@P2, SWITCHOFFSET(SYSDATETIMEOFFSET(), '-06:00')),
        MotivoAnulacion = @P3
    WHERE ID = @P4;
END
GO
GO

-- >>> sql_group2_hr_nomina.sql
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
-- ============================================================================
-- REMEDIACIÓN AUDITORÍA GRUPO 2: RR. HH., Nómina, Pago de Planilla, Vales,
-- Asistencia/Kiosco y Biometría (L04, L05, L12, L17, L19)
-- ============================================================================

SET NOCOUNT ON;
GO

-- 1. L17: Incluir HoraEntrada y HoraSalida en el bloqueo de empleado de Kiosco
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NombreCompleto, HoraEntrada, HoraSalida
    FROM [rrhh].[Empleados] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID = @P1 AND EstadoEmpleado = 'Activo';
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerEmpleadoActivoPorIDBloqueo] TO [db_rol_kiosco];
GO

-- 2. L17: Orden determinista en turno laboral por defecto
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerTurnoLaboralActivoDefecto]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos
    FROM [rrhh].[TurnosLaborales]
    WHERE Activo = 1
    ORDER BY ID ASC;
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerTurnoLaboralActivoDefecto] TO [db_rol_kiosco];
GO

-- 3. L19: Huella ligera de descriptores faciales en BD para sincronizar caché multi-worker
CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerHuellaDescriptoresFacialesKiosco]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        COUNT(*) AS TotalActivos,
        ISNULL(MAX(ID), 0) AS MaxID,
        ISNULL(CHECKSUM_AGG(BINARY_CHECKSUM(ID, CAST(FaceDescriptor AS VARCHAR(4000)))), 0) AS Huella
    FROM [rrhh].[Empleados]
    WHERE EstadoEmpleado = 'Activo' AND FaceDescriptor IS NOT NULL;
END
GO

GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerHuellaDescriptoresFacialesKiosco] TO [db_rol_kiosco];
GO

-- 4. L12: Vales en nómina filtrados por fecha del período y aplicación parcial sin neto negativo
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSumaValesPendientesUsuario]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Monto), 0)
    FROM [rrhh].[ValesEmpleados]
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2);
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ListarValesPendientesUsuarioHastaFecha]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Monto, Fecha
    FROM [rrhh].[ValesEmpleados] WITH (UPDLOCK, HOLDLOCK)
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2)
    ORDER BY Fecha ASC, ID ASC;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarValeDescontadoPorID]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Descontado = 1
    WHERE ID = @P1 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_ActualizarSaldoValeParcialPorID]
    @P1 DECIMAL(10,2) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Monto = @P1, Descontado = 0
    WHERE ID = @P2 AND Descontado = 0;
END
GO

CREATE OR ALTER PROCEDURE [contabilidad].[sp_MarcarValesDescontadosUsuario]
    @P1 INT = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[ValesEmpleados]
    SET Descontado = 1
    WHERE EmpleadoID = @P1
      AND Descontado = 0
      AND (@P2 IS NULL OR CAST(Fecha AS DATE) <= @P2);
END
GO

-- 5. L05: Desembolso verificable de nómina (control de fondos en Caja/Bancos y transición a Pagada)
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoDisponibleCuentaBloqueo]
    @P1 VARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(d.Debe - d.Haber), 0) AS SaldoDisponible
    FROM [contabilidad].[CatalogoCuentas] c WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [contabilidad].[DetalleAsientos] d WITH (UPDLOCK, HOLDLOCK)
        ON d.CuentaID = c.ID
    LEFT JOIN [contabilidad].[AsientosDiario] a WITH (UPDLOCK, HOLDLOCK)
        ON a.ID = d.AsientoID AND a.Estado = 'Contabilizado'
    WHERE c.Codigo = @P1 AND c.Activa = 1;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_VerificarAsientoPagoNominaExistente]
    @P1 VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 ID, NumeroComprobante
    FROM [contabilidad].[AsientosDiario] WITH (UPDLOCK, HOLDLOCK)
    WHERE ReferenciaExterna = @P1 AND Estado = 'Contabilizado'
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_MarcarNominaPagada]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[Nomina]
    SET Estado = 'Pagada'
    WHERE ID = @P1 AND Estado = 'Contabilizada';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarNominasContabilizadasPorPeriodoBloqueo]
    @P1 DATE = NULL,
    @P2 DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID
    FROM [rrhh].[Nomina] WITH (UPDLOCK, HOLDLOCK)
    WHERE PeriodoInicio >= @P1 AND PeriodoFin <= @P2 AND Estado = 'Contabilizada'
    ORDER BY ID ASC;
END
GO
GO

-- >>> sql_group3_accounting_dgi.sql
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
-- ============================================================================
-- Group 3 Remediation SQL: Accounting, Balance Sheet, DGI Engine/Repo & Forecast
-- Target Database: PanaderiaQA_Prevalidacion_20261015
-- ============================================================================
SET NOCOUNT ON;
GO

-- 1. L24: Saldo disponible con bloqueo UPDLOCK, HOLDLOCK sobre cuentas de efectivo/bancos
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerSaldoDisponibleCuenta]
    @CodigoCuenta NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        C.Naturaleza,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
        ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber
    FROM [contabilidad].[CatalogoCuentas] C WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [contabilidad].[DetalleAsientos] D WITH (UPDLOCK, HOLDLOCK) ON D.CuentaID = C.ID
    LEFT JOIN [contabilidad].[AsientosDiario] A WITH (UPDLOCK, HOLDLOCK) ON D.AsientoID = A.ID
        AND (
            A.Estado = 'Contabilizado'
            OR (A.Estado = 'Anulado' AND EXISTS (
                SELECT 1
                FROM [contabilidad].[AsientosDiario] R
                WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
                  AND R.Estado = 'Contabilizado'
            ))
        )
    WHERE C.Codigo = @CodigoCuenta
    GROUP BY C.Naturaleza;
END
GO

-- 2. L27: Verificación de conciliación de facturas y compras antes del cierre mensual
CREATE OR ALTER PROCEDURE [contabilidad].[sp_VerificarConciliacionCierrePeriodo]
    @PeriodoID INT,
    @Mes INT,
    @Anio INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @FacturasSinAsiento INT = 0;
    DECLARE @ComprasSinAsiento INT = 0;

    SELECT @FacturasSinAsiento = COUNT(*)
    FROM [ventas].[Facturas] f
    WHERE MONTH(f.FechaHora) = @Mes
      AND YEAR(f.FechaHora) = @Anio
      AND ISNULL(f.EstadoFiscal, 'Emitida') != 'Anulada'
      AND NOT EXISTS (
          SELECT 1
          FROM [contabilidad].[AsientosDiario] a
          WHERE a.Estado = 'Contabilizado'
            AND (
                a.ID = TRY_CONVERT(INT, JSON_VALUE(CASE WHEN ISJSON(f.DocumentoJSON) = 1 THEN f.DocumentoJSON ELSE N'{}' END, '$.asiento_id'))
                OR a.ReferenciaExterna = f.NumeroFactura
                OR a.ReferenciaExterna = CONCAT('FAC-', f.ID)
                OR a.ReferenciaExterna = CAST(f.ID AS NVARCHAR(100))
            )
      );

    SELECT @ComprasSinAsiento = COUNT(*)
    FROM [produccion].[ComprasMateriaPrima] c
    WHERE MONTH(c.Fecha) = @Mes
      AND YEAR(c.Fecha) = @Anio
      AND NOT EXISTS (
          SELECT 1
          FROM [contabilidad].[AsientosDiario] a
          WHERE a.Estado = 'Contabilizado'
            AND (
                a.ReferenciaExterna = CONCAT('COMP-', c.ID)
                OR (c.FacturaProveedor IS NOT NULL AND LTRIM(RTRIM(c.FacturaProveedor)) <> '' AND a.ReferenciaExterna = c.FacturaProveedor)
                OR a.ReferenciaExterna = CAST(c.ID AS NVARCHAR(100))
            )
      );

    SELECT @FacturasSinAsiento AS FacturasSinAsiento, @ComprasSinAsiento AS ComprasSinAsiento;
END
GO

-- 3. L14: Resumen financiero de rango (Utilidad neta contable real vs Flujo de caja operativo)
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerResumenFinancieroRango]
    @FechaInicio DATETIME2,
    @FechaFin DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ISNULL(SUM(CASE WHEN C.Clase = 'Ingreso' OR C.Codigo LIKE '4.%' THEN D.Haber - D.Debe ELSE 0 END), 0) AS IngresosContables,
        ISNULL(SUM(CASE WHEN C.Clase = 'Costo' OR C.Codigo LIKE '5.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS CostosContables,
        ISNULL(SUM(CASE WHEN C.Clase = 'Gasto' OR C.Codigo LIKE '6.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS GastosContables,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                           AND A.Estado = 'Contabilizado' AND ISNULL(A.TipoDocumento, N'') != N'Reversión'
                     THEN D.Debe ELSE 0 END), 0) AS EntradasEfectivo,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                           AND A.Estado = 'Contabilizado' AND ISNULL(A.TipoDocumento, N'') != N'Reversión'
                     THEN D.Haber ELSE 0 END), 0) AS SalidasEfectivo,
        ISNULL(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                     THEN D.Debe - D.Haber ELSE 0 END), 0) AS FlujoCajaOperativo
    FROM [contabilidad].[DetalleAsientos] D
    JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
    JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
    WHERE (
        A.Estado = 'Contabilizado'
        OR (A.Estado = 'Anulado' AND EXISTS (
            SELECT 1
            FROM [contabilidad].[AsientosDiario] R
            WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
              AND R.Estado = 'Contabilizado'
        ))
    )
      AND A.Fecha >= @FechaInicio
      AND A.Fecha < @FechaFin;
END
GO

-- 4. L22: Balance General con separación de Resultados Acumulados Anteriores vs Utilidad del Ejercicio
CREATE OR ALTER PROCEDURE [contabilidad].[sp_ObtenerBalanceGeneralCorte]
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @InicioEjercicio DATE = DATEFROMPARTS(YEAR(@FechaCorte), 1, 1);
    DECLARE @FinExclusivo DATE = DATEADD(DAY, 1, CAST(@FechaCorte AS DATE));

    WITH SaldosHistoricos AS (
        SELECT
            C.Clase,
            C.Grupo,
            C.Codigo,
            C.Nombre AS Cuenta,
            C.Naturaleza,
            SUM(D.Debe) AS TotalDebe,
            SUM(D.Haber) AS TotalHaber,
            SUM(CASE WHEN A.Fecha < @InicioEjercicio THEN D.Debe ELSE 0 END) AS DebeAnterior,
            SUM(CASE WHEN A.Fecha < @InicioEjercicio THEN D.Haber ELSE 0 END) AS HaberAnterior,
            SUM(CASE WHEN A.Fecha >= @InicioEjercicio THEN D.Debe ELSE 0 END) AS DebeEjercicio,
            SUM(CASE WHEN A.Fecha >= @InicioEjercicio THEN D.Haber ELSE 0 END) AS HaberEjercicio
        FROM [contabilidad].[DetalleAsientos] D
        JOIN [contabilidad].[AsientosDiario] A ON D.AsientoID = A.ID
        JOIN [contabilidad].[CatalogoCuentas] C ON D.CuentaID = C.ID
        WHERE (
            A.Estado = 'Contabilizado'
            OR (A.Estado = 'Anulado' AND EXISTS (
                SELECT 1
                FROM [contabilidad].[AsientosDiario] R
                WHERE R.ReferenciaExterna = CONCAT('REV-', A.ID)
                  AND R.Estado = 'Contabilizado'
            ))
        )
          AND A.Fecha < @FinExclusivo
        GROUP BY C.Clase, C.Grupo, C.Codigo, C.Nombre, C.Naturaleza
    )
    SELECT
        Clase,
        Grupo,
        Codigo,
        Cuenta,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (TotalDebe - TotalHaber)
            ELSE (TotalHaber - TotalDebe)
        END AS SaldoFinal,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (DebeAnterior - HaberAnterior)
            ELSE (HaberAnterior - DebeAnterior)
        END AS SaldoEjerciciosAnteriores,
        CASE
            WHEN Naturaleza = 'Deudora' THEN (DebeEjercicio - HaberEjercicio)
            ELSE (HaberEjercicio - DebeEjercicio)
        END AS SaldoEjercicioActual
    FROM SaldosHistoricos
    WHERE (TotalDebe - TotalHaber) <> 0
       OR (DebeAnterior - HaberAnterior) <> 0
       OR (DebeEjercicio - HaberEjercicio) <> 0
    ORDER BY Codigo;
END
GO

-- 5. L06 & L07: Snapshot DGI de Ventas Candidatas con asiento_id y reversion_asiento_id
CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIVentasCandidatas]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL,
    @P3 DATETIME2 = NULL,
    @P4 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        f.ID AS id,
        f.NumeroFactura AS numero,
        f.FechaHora AS fecha,
        f.Subtotal AS base,
        f.IVA AS iva,
        f.Total AS total,
        f.EstadoFiscal AS estado,
        f.FechaAnulacion AS anulada_en,
        f.MotivoAnulacion AS motivo_anulacion,
        f.DocumentoJSON AS documento,
        j.AsientoID AS asiento_id,
        a.Fecha AS fecha_asiento,
        r.ID AS reversion_asiento_id,
        r.Fecha AS fecha_reversion
    FROM [ventas].[Facturas] f
    OUTER APPLY (
        SELECT COALESCE(
            TRY_CONVERT(INT, JSON_VALUE(CASE WHEN ISJSON(f.DocumentoJSON) = 1 THEN f.DocumentoJSON ELSE N'{}' END, '$.asiento_id')),
            (SELECT TOP 1 a0.ID FROM [contabilidad].[AsientosDiario] a0 WHERE a0.ReferenciaExterna = f.NumeroFactura ORDER BY a0.ID)
        ) AS AsientoID
    ) j
    LEFT JOIN [contabilidad].[AsientosDiario] a ON a.ID = j.AsientoID
    OUTER APPLY (
        SELECT TOP 1 v.ID, v.Fecha
        FROM [contabilidad].[AsientosDiario] v
        WHERE (
            v.ReferenciaExterna = CONCAT('REV-', j.AsientoID)
            OR v.ReferenciaExterna = CONCAT('REV-', f.NumeroFactura)
            OR v.ReferenciaExterna = CONCAT('REV-FACT-', f.ID)
        )
        ORDER BY v.ID
    ) r
    WHERE (f.FechaHora >= @P1 AND f.FechaHora < @P2)
       OR (f.FechaAnulacion >= @P3 AND f.FechaAnulacion < @P4)
    ORDER BY f.ID;
END
GO

-- 6. L06 & L07: Snapshot DGI de Asientos con tipo_documento
CREATE OR ALTER PROCEDURE [fiscal].[sp_SnapshotDGIAsientos]
    @P1 DATETIME2 = NULL,
    @P2 DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ID AS id,
        NumeroComprobante AS numero,
        Fecha AS fecha,
        Estado AS estado,
        Descripcion AS descripcion,
        ReferenciaExterna AS referencia,
        TipoDocumento AS tipo_documento
    FROM [contabilidad].[AsientosDiario]
    WHERE Fecha >= @P1 AND Fecha < @P2
    ORDER BY ID;
END
GO

-- 7. L11: Historial de Revisiones DGI con Huella para verificación de frescura en GET /admin/dgi
CREATE OR ALTER PROCEDURE [fiscal].[sp_HistorialRevisionesDGIPorPeriodo]
    @PeriodoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 100
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.Huella, r.ResultadoJSON,
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
        r.ID, r.PeriodoID, r.Obligacion, r.Version, r.Estado, r.Motor, r.Huella, r.ResultadoJSON,
        r.CreadoEn, r.CreadoPor, r.AprobadoPor, p.Desde, p.Hasta
    FROM [fiscal].[DGI_Revisiones] r
    JOIN [fiscal].[DGI_Periodos] p ON p.ID = r.PeriodoID
    ORDER BY r.ID DESC;
END
GO

-- 8. L25: Histórico de Ventas para Regresión Lineal anclado a la fecha operativa
CREATE OR ALTER PROCEDURE [ventas].[sp_EstadisticaHistoricoVentasRegresion]
    @FechaHoy DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Corte DATE = ISNULL(@FechaHoy, CONVERT(date, GETDATE()));
    SELECT CONVERT(date, FechaHora) AS Dia, ISNULL(SUM(Total), 0) AS Total
    FROM [ventas].[Facturas]
    WHERE EstadoFiscal = 'Emitida'
      AND CONVERT(date, FechaHora) >= DATEADD(DAY, -29, @Corte)
      AND CONVERT(date, FechaHora) <= @Corte
    GROUP BY CONVERT(date, FechaHora)
    ORDER BY Dia;
END
GO
GO

-- >>> sql_group4_auth_inv_prod.sql
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
/* ============================================================================
   REMEDIACIÓN AUDITORÍA GRUPO 4 (L08, L09, L10, L16, L18, L20, L21, L23, L26)
   Archivo: scratch/remediation_20261025/sql_group4_auth_inv_prod.sql
   Base de datos objetivo: PanaderiaQA_Prevalidacion_20261015
   ============================================================================ */

SET NOCOUNT ON;
GO

-- ============================================================================
-- 1. AJUSTES DE ESQUEMA IDEMPOTENTES (L10, L18, L20)
-- ============================================================================
IF COL_LENGTH('produccion.Proveedores', 'RUC') IS NULL
BEGIN
    ALTER TABLE [produccion].[Proveedores] ADD [RUC] NVARCHAR(30) NULL;
END
GO

IF COL_LENGTH('produccion.ComprasMateriaPrima', 'IdempotencyKey') IS NULL
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD [IdempotencyKey] NVARCHAR(120) NULL;
END
GO

IF COL_LENGTH('produccion.ComprasMateriaPrima', 'ProveedorRUC') IS NULL
BEGIN
    ALTER TABLE [produccion].[ComprasMateriaPrima] ADD [ProveedorRUC] NVARCHAR(30) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'produccion.ComprasMateriaPrima')
      AND name = N'UX_ComprasMateriaPrima_IdempotencyKey'
)
BEGIN
    CREATE UNIQUE INDEX [UX_ComprasMateriaPrima_IdempotencyKey]
    ON [produccion].[ComprasMateriaPrima]([IdempotencyKey])
    WHERE [IdempotencyKey] IS NOT NULL;
END
GO

IF COL_LENGTH('produccion.MateriaPrima', 'CostoUnitario') IS NULL
BEGIN
    ALTER TABLE [produccion].[MateriaPrima] ADD [CostoUnitario] DECIMAL(18, 4) NULL;
END
GO

-- ============================================================================
-- 2. L08: NORMALIZACIÓN DE IDENTIDAD EN BLOQUEO DE LOGIN
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_VerificarBloqueoCuenta]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Ahora DATETIME2 = SYSDATETIME();
    DECLARE @Raw NVARCHAR(100) = LOWER(LTRIM(RTRIM(ISNULL(@Identificador, N'desconocido'))));
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@Raw, N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    DECLARE @Canon NVARCHAR(100) = @Raw;

    IF @Clean LIKE N'[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 8
        SET @Canon = N'+505' + @Clean;
    ELSE IF @Clean LIKE N'505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 11
        SET @Canon = N'+505' + RIGHT(@Clean, 8);
    ELSE IF @Clean LIKE N'00505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 13
        SET @Canon = N'+505' + RIGHT(@Clean, 8);

    SET @DireccionIP = LTRIM(RTRIM(ISNULL(@DireccionIP, '0.0.0.0')));

    SELECT TOP 1
        ID,
        Identificador,
        DireccionIP,
        IntentosFallidos,
        BloqueadoHasta,
        CASE WHEN BloqueadoHasta IS NOT NULL AND BloqueadoHasta > @Ahora THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS EstaBloqueado
    FROM [seguridad].[BloqueosCuenta]
    WHERE Identificador IN (@Canon, @Raw)
      AND DireccionIP = @DireccionIP
      AND BloqueadoHasta > @Ahora
    ORDER BY BloqueadoHasta DESC;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_VerificarBloqueoLogin]
    @Identificador NVARCHAR(100),
    @DireccionIP VARCHAR(45)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC [seguridad].[sp_VerificarBloqueoCuenta]
        @Identificador = @Identificador,
        @DireccionIP = @DireccionIP;
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
        DECLARE @Raw NVARCHAR(100) = LOWER(LTRIM(RTRIM(ISNULL(@Identificador, N'desconocido'))));
        DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@Raw, N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
        SET @Identificador = @Raw;

        IF @Clean LIKE N'[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 8
            SET @Identificador = N'+505' + @Clean;
        ELSE IF @Clean LIKE N'505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 11
            SET @Identificador = N'+505' + RIGHT(@Clean, 8);
        ELSE IF @Clean LIKE N'00505[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND LEN(@Clean) = 13
            SET @Identificador = N'+505' + RIGHT(@Clean, 8);

        SET @DireccionIP = LTRIM(RTRIM(ISNULL(@DireccionIP, '0.0.0.0')));

        SELECT @MaxIntentos = ISNULL(TRY_CAST(Valor AS INT), @MaxIntentos)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_intentos_max';

        SELECT @MinutosBloqueo = ISNULL(TRY_CAST(Valor AS INT), @MinutosBloqueo)
        FROM [seguridad].[ConfiguracionSistema] WHERE Clave = 'smtp_bloqueo_minutos';

        IF @Exitoso = 1
        BEGIN
            DELETE FROM [seguridad].[BloqueosCuenta]
            WHERE Identificador IN (@Identificador, @Raw) AND DireccionIP = @DireccionIP;

            SELECT
                CAST(0 AS BIT) AS Bloqueado,
                CAST(0 AS BIT) AS RecienBloqueado,
                0 AS IntentosFallidos,
                CAST(NULL AS DATETIME2) AS BloqueadoHasta;
            RETURN;
        END

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

-- ============================================================================
-- 3. L09: CONTEO ACUMULADO DE FALLOS TOTP POR CUENTA EN VENTANA DE TIEMPO
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_ObtenerFallosTOTPRecientes]
    @Subject NVARCHAR(128),
    @MinExpiresAt BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ISNULL(SUM(Attempts), 0) AS TotalFallos
    FROM [seguridad].[AuthChallenges] WITH (UPDLOCK, HOLDLOCK)
    WHERE Subject = @Subject
      AND Kind LIKE 'totp%'
      AND Verified = 0
      AND ExpiresAt > @MinExpiresAt;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_LimpiarFallosTOTPUsuario]
    @Subject NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [seguridad].[AuthChallenges]
    SET Verified = 1,
        Consumed = 1,
        Attempts = 0
    WHERE Subject = @Subject
      AND Kind LIKE 'totp%';
END
GO

-- ============================================================================
-- 4. L23: INVARIANTE DE ÚLTIMO SUPERADMIN ACTIVO BAJO BLOQUEO SERIALIZABLE
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_ContarSuperAdminsActivosBloqueo]
    @TargetUserID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @SuperAdminRolID INT;
    SELECT @SuperAdminRolID = ID
    FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
    WHERE Nombre = 'SuperAdmin';

    DECLARE @TargetRolID INT, @TargetActivo BIT, @TargetRolNombre NVARCHAR(50);
    SELECT @TargetRolID = u.RolID, @TargetActivo = u.Activo, @TargetRolNombre = r.Nombre
    FROM [seguridad].[Usuarios] u WITH (UPDLOCK, HOLDLOCK)
    JOIN [seguridad].[Roles] r ON r.ID = u.RolID
    WHERE u.ID = @TargetUserID;

    DECLARE @Restantes INT = 0;
    SELECT @Restantes = COUNT(*)
    FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
    WHERE RolID = @SuperAdminRolID
      AND Activo = 1
      AND ID <> ISNULL(@TargetUserID, -1);

    SELECT
        @TargetRolID AS TargetRolID,
        @TargetRolNombre AS TargetRolNombre,
        @TargetActivo AS TargetActivo,
        @SuperAdminRolID AS SuperAdminRolID,
        ISNULL(@Restantes, 0) AS SuperAdminsActivosRestantes;
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarRolUsuario]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P1;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @P2 <> @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @P1;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET RolID = @P2
        WHERE ID = @P1;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ActualizarRolUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ActualizarUsuario]
    @UsuarioID INT,
    @NombreCompleto NVARCHAR(100) = NULL,
    @RolID INT = NULL,
    @Activo BIT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        DECLARE @NuevoRolID INT = ISNULL(@RolID, @RolActualID);
        DECLARE @NuevoActivo BIT = ISNULL(@Activo, @ActivoActual);

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
           AND (@NuevoRolID <> @SuperAdminRolID OR @NuevoActivo = 0)
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET NombreCompleto = ISNULL(@NombreCompleto, NombreCompleto),
            RolID = @NuevoRolID,
            Activo = @NuevoActivo
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ActualizarUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ToggleActivoUsuario]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P1;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @P1;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 1 ^ Activo
        WHERE ID = @P1;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_ToggleActivoUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_CambiarEstadoUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 1 ^ Activo
        OUTPUT DELETED.NombreCompleto, DELETED.Username, DELETED.RolID, DELETED.Activo AS ActivoAntes, INSERTED.Activo AS ActivoDespues
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_CambiarEstadoUsuario';
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_EliminarUsuario]
    @UsuarioID INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @SuperAdminRolID INT;
        SELECT @SuperAdminRolID = ID
        FROM [seguridad].[Roles] WITH (UPDLOCK, HOLDLOCK)
        WHERE Nombre = 'SuperAdmin';

        DECLARE @RolActualID INT, @ActivoActual BIT;
        SELECT @RolActualID = RolID, @ActivoActual = Activo
        FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @UsuarioID;

        IF @RolActualID IS NULL
            THROW 52004, 'Usuario no encontrado.', 1;

        IF @RolActualID = @SuperAdminRolID AND @ActivoActual = 1
        BEGIN
            DECLARE @Restantes INT = 0;
            SELECT @Restantes = COUNT(*)
            FROM [seguridad].[Usuarios] WITH (UPDLOCK, HOLDLOCK)
            WHERE RolID = @SuperAdminRolID AND Activo = 1 AND ID <> @UsuarioID;

            IF ISNULL(@Restantes, 0) < 1
                THROW 52005, 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema', 1;
        END

        UPDATE [seguridad].[Usuarios]
        SET Activo = 0
        WHERE ID = @UsuarioID;

        IF @OwnTran = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'seguridad.sp_EliminarUsuario';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 5. L26: ALERTAS SMTP OUTBOX CON DESTINATARIO INDIVIDUAL PERSISTIDO
-- ============================================================================
CREATE OR ALTER PROCEDURE [seguridad].[sp_EncolarAlertaSMTP]
    @ErrorID BIGINT,
    @DestinatariosJSON NVARCHAR(MAX) = NULL,
    @Forzar BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @LockResult INT;
        EXEC @LockResult = sys.sp_getapplock @Resource = N'panaderia.smtp.outbox.v1',
             @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;

        INSERT INTO [seguridad].[AlertasSMTPOutbox](ErrorID, DedupKey, DestinatariosJSON, Forzar)
        SELECT b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError, 120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)), @DestinatariosJSON, @Forzar
        FROM [seguridad].[BitacoraErrores] b
        WHERE b.ID = @ErrorID AND b.NotificadoSMTP = 0
          AND NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] o WHERE o.ErrorID = b.ID);

        UPDATE [seguridad].[AlertasSMTPOutbox]
        SET DestinatariosJSON = COALESCE(@DestinatariosJSON, DestinatariosJSON),
            Forzar = CASE WHEN @Forzar = 1 THEN 1 ELSE Forzar END
        WHERE ErrorID = @ErrorID AND Estado <> 'Sent';

        COMMIT;
        SELECT CAST(CASE WHEN EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] WHERE ErrorID = @ErrorID)
                        THEN 1 ELSE 0 END AS BIT) AS Encolada;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE [seguridad].[sp_ReclamarAlertaSMTP]
    @ErrorID BIGINT = NULL,
    @VentanaSegundos INT = 300,
    @LeaseSegundos INT = 300,
    @SembrarLote INT = 20
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @SembrarLote NOT BETWEEN 0 AND 100 OR @VentanaSegundos NOT BETWEEN 0 AND 86400
       OR @LeaseSegundos NOT BETWEEN 60 AND 3600
        THROW 51071, 'Limites SMTP invalidos.', 1;
    DECLARE @Ahora DATETIME2(3) = SYSUTCDATETIME(), @Elegido BIGINT, @Clave BINARY(32),
            @Token UNIQUEIDENTIFIER = NEWID(), @LockResult INT;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC @LockResult = sys.sp_getapplock @Resource = N'panaderia.smtp.outbox.v1',
             @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
        IF @LockResult < 0 THROW 51070, 'No se pudo reservar la cola SMTP.', 1;

        INSERT INTO [seguridad].[AlertasSMTPOutbox](ErrorID, DedupKey)
        SELECT TOP (@SembrarLote) b.ID, HASHBYTES('SHA2_256', (
            SELECT b.Origen AS origen, b.NumeroError AS numero, b.Procedimiento AS procedimiento,
                CASE WHEN b.Procedimiento IS NULL AND b.NumeroError IS NULL
                     THEN LEFT(b.MensajeError, 120) ELSE N'' END AS mensaje
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER))
        FROM [seguridad].[BitacoraErrores] b
        WHERE b.NotificadoSMTP = 0
          AND NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPOutbox] o WHERE o.ErrorID = b.ID)
        ORDER BY b.ID;

        UPDATE TOP (100) o SET Estado = 'Suppressed', ClaimToken = NULL, LeaseHasta = NULL
        FROM [seguridad].[AlertasSMTPOutbox] o
        JOIN [seguridad].[AlertasSMTPDedup] d ON d.DedupKey = o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.Forzar = 0
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta <= @Ahora)
          AND d.UltimoEnvio > DATEADD(SECOND, -@VentanaSegundos, @Ahora)
          AND (@ErrorID IS NULL OR o.ErrorID = @ErrorID);

        SELECT TOP(1) @Elegido = o.ErrorID, @Clave = o.DedupKey
        FROM [seguridad].[AlertasSMTPOutbox] o
        LEFT JOIN [seguridad].[AlertasSMTPDedup] d ON d.DedupKey = o.DedupKey
        WHERE o.Estado IN ('Pending', 'Sending') AND o.DisponibleDesde <= @Ahora
          AND (o.LeaseHasta IS NULL OR o.LeaseHasta <= @Ahora)
          AND (d.LeaseHasta IS NULL OR d.LeaseHasta <= @Ahora)
          AND (o.Forzar = 1 OR d.UltimoEnvio IS NULL OR d.UltimoEnvio <= DATEADD(SECOND, -@VentanaSegundos, @Ahora))
          AND (@ErrorID IS NULL OR o.ErrorID = @ErrorID)
        ORDER BY CASE WHEN o.DestinatariosJSON IS NOT NULL THEN 0 ELSE 1 END,
                 o.Forzar DESC,
                 o.DisponibleDesde,
                 o.ErrorID;

        IF @Elegido IS NOT NULL
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM [seguridad].[AlertasSMTPDedup] WHERE DedupKey = @Clave)
                INSERT INTO [seguridad].[AlertasSMTPDedup](DedupKey) VALUES(@Clave);
            UPDATE [seguridad].[AlertasSMTPDedup]
               SET ClaimToken = @Token, LeaseHasta = DATEADD(SECOND, @LeaseSegundos, @Ahora)
             WHERE DedupKey = @Clave;
            UPDATE [seguridad].[AlertasSMTPOutbox] SET Estado = 'Sending', ClaimToken = @Token,
                   LeaseHasta = DATEADD(SECOND, @LeaseSegundos, @Ahora), Intentos = Intentos + 1
             WHERE ErrorID = @Elegido;
        END;
        COMMIT;
        SELECT b.*, o.ClaimToken, o.DestinatariosJSON, o.DestinatariosJSON AS Destinatario
        FROM [seguridad].[AlertasSMTPOutbox] o
        JOIN [seguridad].[BitacoraErrores] b ON b.ID = o.ErrorID
        WHERE o.ErrorID = @Elegido AND o.ClaimToken = @Token;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 6. L16: CLIENTES - NORMALIZACIÓN Y UNICIDAD DE TELÉFONO BAJO BLOQUEO
-- ============================================================================
CREATE OR ALTER PROCEDURE [crm].[sp_VerificarTelefonoClienteDuplicado]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P1, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    SELECT ID
    FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
    WHERE ID <> ISNULL(@P2, 0)
      AND ID > 1
      AND Telefono IS NOT NULL
      AND LTRIM(RTRIM(Telefono)) <> ''
      AND (
          CASE
              WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                   AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
              THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
              WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 13
                   AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 5) = '00505'
              THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
              ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
          END = @Clean
      );
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
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P3, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID <> ISNULL(@P7, 0)
          AND ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 13
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 5) = '00505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    SET NOCOUNT OFF;
    UPDATE [crm].[Clientes]
    SET Nombre = @P1,
        Apellidos = @P2,
        Telefono = @Clean,
        Genero = @P4,
        FechaNacimiento = @P5,
        NivelConfianzaID = @P6
    WHERE ID = @P7 AND ID > 1;
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
        DECLARE @Clean VARCHAR(30) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '');
        IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = '505'
            SET @Clean = RIGHT(@Clean, 8);
        ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = '00505'
            SET @Clean = RIGHT(@Clean, 8);

        IF EXISTS (
            SELECT 1
            FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
            WHERE ID <> @ClienteID
              AND ID > 1
              AND Telefono IS NOT NULL
              AND (
                  CASE
                      WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                           AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                      THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                      ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
                  END = @Clean
              )
        )
            THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

        IF NOT EXISTS (SELECT 1 FROM [crm].[NivelesConfianza] WHERE ID = @NivelConfianzaID)
            THROW 52021, 'Nivel de fidelidad inexistente.', 1;

        UPDATE [crm].[Clientes]
        SET Nombre = @Nombre,
            Apellidos = @Apellidos,
            Telefono = @Clean,
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
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P3, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    INSERT INTO [crm].[Clientes] (
        Nombre, Apellidos, Telefono, PasswordHash, Genero,
        FechaNacimiento, RutaFotoPerfil, EsInvitado, NivelConfianzaID
    )
    VALUES (@P1, @P2, @Clean, @P4, @P5, @P6, @P7, 0, 1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_InsertarClienteRapido]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean NVARCHAR(100) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@P2, N''))), N' ', N''), N'-', N''), N'(', N''), N')', N''), N'.', N''), N'+', N'');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = N'505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = N'00505'
        SET @Clean = RIGHT(@Clean, 8);

    IF @Clean <> N'' AND EXISTS (
        SELECT 1
        FROM [crm].[Clientes] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID > 1
          AND Telefono IS NOT NULL
          AND LTRIM(RTRIM(Telefono)) <> ''
          AND (
              CASE
                  WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                       AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
                  THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
                  ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
              END = @Clean
          )
    )
        THROW 52020, 'El teléfono ya pertenece a otro cliente.', 1;

    INSERT INTO [crm].[Clientes](Nombre, Telefono, NivelConfianzaID)
    OUTPUT INSERTED.ID
    VALUES(@P1, CASE WHEN @Clean <> N'' THEN @Clean ELSE @P2 END, 1);
END
GO

CREATE OR ALTER PROCEDURE [crm].[sp_ObtenerClientePorTelefono]
    @Telefono VARCHAR(30)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Clean VARCHAR(30) = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(@Telefono, ''))), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '');
    IF LEN(@Clean) = 11 AND LEFT(@Clean, 3) = '505'
        SET @Clean = RIGHT(@Clean, 8);
    ELSE IF LEN(@Clean) = 13 AND LEFT(@Clean, 5) = '00505'
        SET @Clean = RIGHT(@Clean, 8);

    SELECT ID, Nombre, Apellidos, Telefono, PasswordHash, EsInvitado, NivelConfianzaID, FechaNacimiento, RutaFotoPerfil
    FROM [crm].[Clientes]
    WHERE Telefono = @Telefono
       OR (
           @Clean <> '' AND Telefono IS NOT NULL AND
           CASE
               WHEN LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')) = 11
                    AND LEFT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 3) = '505'
               THEN RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', ''), 8)
               ELSE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Telefono)), ' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '')
           END = @Clean
       )
    ORDER BY EsInvitado ASC, ID DESC;
END
GO

-- ============================================================================
-- 7. L10 y L18: COMPRAS IDEMPOTENTES Y SOPORTE RUC DE PROVEEDOR PARA IVA
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_CrearProveedor]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [produccion].[Proveedores] (Nombre, Telefono, RUC)
    OUTPUT INSERTED.ID
    VALUES (@P1, @P2, @P3);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarProveedorActivo]
    @P1 NVARCHAR(255) = NULL,
    @P2 NVARCHAR(255) = NULL,
    @P3 INT = NULL,
    @P4 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT OFF;
    UPDATE [produccion].[Proveedores]
    SET Nombre = @P1,
        Telefono = @P2,
        RUC = COALESCE(@P4, RUC)
    WHERE ID = @P3 AND Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_VerificarProveedorActivo]
    @P1 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, RUC FROM [produccion].[Proveedores] WHERE ID = @P1 AND Activo = 1;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ListarProveedoresActivos]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Nombre, Telefono, RUC
    FROM [produccion].[Proveedores]
    WHERE Activo = 1
    ORDER BY Nombre;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerCompraPorIdempotencia]
    @IdempotencyKey NVARCHAR(120),
    @ProveedorID INT = NULL,
    @FacturaProveedor NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1
        ID,
        MateriaPrimaID,
        ProveedorID,
        Cantidad,
        CostoTotal,
        FacturaProveedor,
        IVADocumentado,
        Fecha,
        IdempotencyKey
    FROM [produccion].[ComprasMateriaPrima] WITH (UPDLOCK, HOLDLOCK)
    WHERE IdempotencyKey = @IdempotencyKey
       OR (
           @ProveedorID IS NOT NULL
           AND @FacturaProveedor IS NOT NULL
           AND ProveedorID = @ProveedorID
           AND UPPER(LTRIM(RTRIM(FacturaProveedor))) = UPPER(LTRIM(RTRIM(@FacturaProveedor)))
       )
    ORDER BY ID DESC;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarCompraMateriaPrima]
    @P1 INT = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 DECIMAL(18, 2) = NULL,
    @P5 NVARCHAR(255) = NULL,
    @P6 DECIMAL(18, 2) = NULL,
    @P7 DATETIME2 = NULL,
    @P8 NVARCHAR(120) = NULL,
    @P9 NVARCHAR(30) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @P8 IS NOT NULL
    BEGIN
        DECLARE @ExistingID INT;
        SELECT TOP 1 @ExistingID = ID
        FROM [produccion].[ComprasMateriaPrima] WITH (UPDLOCK, HOLDLOCK)
        WHERE IdempotencyKey = @P8;

        IF @ExistingID IS NOT NULL
        BEGIN
            SELECT @ExistingID AS ID, CAST(1 AS BIT) AS YaExistia;
            RETURN;
        END
    END

    INSERT INTO [produccion].[ComprasMateriaPrima] (
        MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, FacturaProveedor, IVADocumentado, Fecha, IdempotencyKey, ProveedorRUC
    )
    OUTPUT INSERTED.ID, CAST(0 AS BIT) AS YaExistia
    VALUES (@P1, @P2, @P3, @P4, @P5, @P6, @P7, @P8, @P9);
END
GO

-- ============================================================================
-- 8. L20: INVENTARIO / RECETAS - CAMBIO DE UNIDAD DE MEDIDA CON CONVERSIÓN
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_ObtenerEstadoMateriaPrimaParaEdicion]
    @MateriaID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        m.ID,
        m.Nombre,
        m.UnidadMedidaID,
        m.StockActual,
        m.StockMinimo,
        m.CostoUnitario,
        (SELECT COUNT(*) FROM [produccion].[RecetaProducto] WHERE MateriaPrimaID = m.ID) AS TotalRecetas,
        (SELECT COUNT(*) FROM [produccion].[ComprasMateriaPrima] WHERE MateriaPrimaID = m.ID) AS TotalCompras,
        (SELECT COUNT(*) FROM [produccion].[ConsumoLote] WHERE MateriaPrimaID = m.ID) AS TotalConsumos
    FROM [produccion].[MateriaPrima] m WITH (UPDLOCK, HOLDLOCK)
    WHERE m.ID = @MateriaID;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_ActualizarMateriaPrima]
    @P1 NVARCHAR(255) = NULL,
    @P2 INT = NULL,
    @P3 DECIMAL(18, 2) = NULL,
    @P4 INT = NULL,
    @FactorConversion DECIMAL(18, 6) = NULL,
    @UsuarioID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        DECLARE @UnidadActualID INT,
                @StockActual DECIMAL(18, 2),
                @StockMinimoActual DECIMAL(18, 2),
                @CostoUnitarioActual DECIMAL(18, 4);

        SELECT
            @UnidadActualID = UnidadMedidaID,
            @StockActual = StockActual,
            @StockMinimoActual = StockMinimo,
            @CostoUnitarioActual = CostoUnitario
        FROM [produccion].[MateriaPrima] WITH (UPDLOCK, HOLDLOCK)
        WHERE ID = @P4;

        IF @UnidadActualID IS NULL
        BEGIN
            IF @OwnTran = 1 COMMIT TRANSACTION;
            SET NOCOUNT OFF;
            UPDATE [produccion].[MateriaPrima] SET Nombre = @P1 WHERE ID = @P4 AND 1 = 0;
            RETURN;
        END

        IF @P2 <> @UnidadActualID
        BEGIN
            DECLARE @TieneUso BIT = 0;
            IF @StockActual > 0
               OR EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE MateriaPrimaID = @P4)
               OR EXISTS (SELECT 1 FROM [produccion].[ComprasMateriaPrima] WHERE MateriaPrimaID = @P4)
               OR EXISTS (SELECT 1 FROM [produccion].[ConsumoLote] WHERE MateriaPrimaID = @P4)
            BEGIN
                SET @TieneUso = 1;
            END

            IF @FactorConversion IS NOT NULL AND @FactorConversion <= 0
                THROW 52040, 'El factor de conversión debe ser mayor a cero.', 1;

            IF @TieneUso = 1 AND (@FactorConversion IS NULL OR @FactorConversion <= 0)
                THROW 52040, 'No se puede cambiar la unidad de medida de una materia prima con stock, recetas o historial sin proporcionar un factor de conversión válido.', 1;

            IF @FactorConversion IS NOT NULL AND @FactorConversion > 0
            BEGIN
                DECLARE @NuevoStock DECIMAL(18, 2) = ROUND(@StockActual * @FactorConversion, 2);
                DECLARE @NuevoMinimo DECIMAL(18, 2) = CASE
                    WHEN @P3 IS NOT NULL AND @P3 <> @StockMinimoActual THEN @P3
                    ELSE ROUND(@StockMinimoActual * @FactorConversion, 2)
                END;
                DECLARE @NuevoCosto DECIMAL(18, 4) = CASE
                    WHEN @CostoUnitarioActual IS NOT NULL THEN ROUND(@CostoUnitarioActual / @FactorConversion, 4)
                    ELSE NULL
                END;

                UPDATE [produccion].[RecetaProducto]
                SET CantidadNecesaria = CASE
                    WHEN ROUND(CantidadNecesaria * @FactorConversion, 2) < 0.01 THEN 0.01
                    ELSE ROUND(CantidadNecesaria * @FactorConversion, 2)
                END
                WHERE MateriaPrimaID = @P4;

                DECLARE @ActorID INT = TRY_CAST(SESSION_CONTEXT(N'usuario_id') AS INT);
                DECLARE @IP VARCHAR(45) = TRY_CAST(SESSION_CONTEXT(N'ip') AS VARCHAR(45));
                DECLARE @AntesJSON NVARCHAR(MAX) = CONCAT(
                    N'{"unidad_id":', @UnidadActualID,
                    N',"stock_actual":', @StockActual,
                    N',"stock_minimo":', @StockMinimoActual, N'}'
                );
                DECLARE @DespuesJSON NVARCHAR(MAX) = CONCAT(
                    N'{"unidad_id":', @P2,
                    N',"factor_conversion":', @FactorConversion,
                    N',"stock_actual":', @NuevoStock,
                    N',"stock_minimo":', @NuevoMinimo, N'}'
                );

                EXEC [seguridad].[sp_RegistrarAuditoria]
                    @UsuarioID = @ActorID,
                    @Accion = 'CONVERTIR_UNIDAD_MP',
                    @Entidad = 'MateriaPrima',
                    @EntidadID = @P4,
                    @DatosAntes = @AntesJSON,
                    @DatosDespues = @DespuesJSON,
                    @IP = @IP;

                SET NOCOUNT OFF;
                UPDATE [produccion].[MateriaPrima]
                SET Nombre = @P1,
                    UnidadMedidaID = @P2,
                    StockActual = @NuevoStock,
                    StockMinimo = @NuevoMinimo,
                    CostoUnitario = @NuevoCosto
                WHERE ID = @P4;

                IF @OwnTran = 1 COMMIT TRANSACTION;
                RETURN;
            END
        END

        SET NOCOUNT OFF;
        UPDATE [produccion].[MateriaPrima]
        SET Nombre = @P1,
            UnidadMedidaID = @P2,
            StockMinimo = @P3
        WHERE ID = @P4;

        IF @OwnTran = 1 COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_ActualizarMateriaPrima';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 9. L21: PRODUCCIÓN - VALIDACIÓN DE PRODUCTO ACTIVO Y NO BEBIDA EN LOTES
-- ============================================================================
CREATE OR ALTER PROCEDURE [produccion].[sp_ValidarProductoParaProduccion]
    @ProductoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.ID,
        p.Nombre,
        p.Activo,
        ISNULL(p.EsFicticio, 0) AS EsFicticio,
        p.CategoriaID,
        ISNULL(c.Nombre, '') AS CategoriaNombre,
        (SELECT COUNT(*) FROM [produccion].[RecetaProducto] r WHERE r.ProductoID = p.ID AND r.CantidadNecesaria > 0) AS TieneReceta
    FROM [catalogo].[Productos] p WITH (UPDLOCK, HOLDLOCK)
    LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
    WHERE p.ID = @ProductoID;
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_InsertarLoteProduccion]
    @P1 INT = NULL,
    @P2 INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Activo BIT, @EsFicticio BIT, @Categoria NVARCHAR(100);
    SELECT
        @Activo = p.Activo,
        @EsFicticio = ISNULL(p.EsFicticio, 0),
        @Categoria = ISNULL(c.Nombre, N'')
    FROM [catalogo].[Productos] p
    LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
    WHERE p.ID = @P1;

    IF @Activo IS NULL
        THROW 52034, 'El producto especificado no existe.', 1;
    IF @Activo = 0
        THROW 52035, 'No se puede registrar un lote de producción para un producto inactivo.', 1;
    IF LOWER(LTRIM(RTRIM(@Categoria))) IN (N'bebidas', N'bebida', N'reventa') OR @EsFicticio = 1
        THROW 52036, 'No se puede registrar un lote de producción para productos de la categoría Bebidas o no producibles.', 1;

    INSERT INTO [produccion].[ProduccionLotes] (ProductoID, CantidadProducida)
    OUTPUT INSERTED.ID
    VALUES (@P1, @P2);
END
GO

CREATE OR ALTER PROCEDURE [produccion].[sp_RegistrarLoteProduccion]
    @ProductoID INT,
    @CantidadProducida INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @OwnTran BIT = 0;
    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @OwnTran = 1;
        END

        IF @CantidadProducida <= 0
            THROW 52031, 'La cantidad a producir debe ser un entero positivo.', 1;

        DECLARE @Activo BIT, @EsFicticio BIT, @Categoria NVARCHAR(100);
        SELECT
            @Activo = p.Activo,
            @EsFicticio = ISNULL(p.EsFicticio, 0),
            @Categoria = ISNULL(c.Nombre, N'')
        FROM [catalogo].[Productos] p
        LEFT JOIN [catalogo].[Categorias] c ON p.CategoriaID = c.ID
        WHERE p.ID = @ProductoID;

        IF @Activo IS NULL
            THROW 52034, 'El producto especificado no existe.', 1;
        IF @Activo = 0
            THROW 52035, 'No se puede registrar un lote de producción para un producto inactivo.', 1;
        IF LOWER(LTRIM(RTRIM(@Categoria))) IN (N'bebidas', N'bebida', N'reventa') OR @EsFicticio = 1
            THROW 52036, 'No se puede registrar un lote de producción para productos de la categoría Bebidas o no producibles.', 1;

        IF NOT EXISTS (SELECT 1 FROM [produccion].[RecetaProducto] WHERE ProductoID = @ProductoID AND CantidadNecesaria > 0)
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

        IF @OwnTran = 1
            COMMIT TRANSACTION;

        SELECT @LoteID AS LoteID;
    END TRY
    BEGIN CATCH
        IF @OwnTran = 1 AND XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        EXEC [seguridad].[sp_RegistrarErrorBD] @Procedimiento = N'produccion.sp_RegistrarLoteProduccion';
        THROW;
    END CATCH
END
GO

-- ============================================================================
-- 10. PERMISOS PARA ROLES DE BASE DE DATOS EN PROCEDIMIENTOS NUEVOS/ACTUALIZADOS
-- ============================================================================
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_VerificarBloqueoLogin] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerFallosTOTPRecientes] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_cajero_pos];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_kiosco];
GRANT EXECUTE ON OBJECT::[seguridad].[sp_LimpiarFallosTOTPUsuario] TO [db_rol_portal_cliente];

GRANT EXECUTE ON OBJECT::[seguridad].[sp_ObtenerConfiguracionGlobal] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[fiscal].[sp_RegistrarBitacoraFiscal] TO [db_rol_produccion];
GRANT EXECUTE ON OBJECT::[ventas].[sp_RegistrarEventoFiscalOperacion] TO [db_rol_produccion];
GO
GO


-- ============================================================================
-- PLANILLA ESTRUCTURADA EN 3 PARTES, VACACIONES, PRESTAMOS Y COBROS POR PERDIDAS (2026-10-25)
-- ============================================================================
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- 1. Agregar columnas a rrhh.Nomina si no existen
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='Viaticos')
    ALTER TABLE [rrhh].[Nomina] ADD [Viaticos] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_Viaticos DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='DepreciacionVehiculo')
    ALTER TABLE [rrhh].[Nomina] ADD [DepreciacionVehiculo] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_DepreciacionVehiculo DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='Incentivos')
    ALTER TABLE [rrhh].[Nomina] ADD [Incentivos] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_Incentivos DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='RiesgoLaboral')
    ALTER TABLE [rrhh].[Nomina] ADD [RiesgoLaboral] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_RiesgoLaboral DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='SueldoExtraordinario')
    ALTER TABLE [rrhh].[Nomina] ADD [SueldoExtraordinario] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_SueldoExtraordinario DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='PrestamosDescontados')
    ALTER TABLE [rrhh].[Nomina] ADD [PrestamosDescontados] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_PrestamosDescontados DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='CobrosPerdidas')
    ALTER TABLE [rrhh].[Nomina] ADD [CobrosPerdidas] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_CobrosPerdidas DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='ProvisionVacaciones')
    ALTER TABLE [rrhh].[Nomina] ADD [ProvisionVacaciones] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_ProvisionVacaciones DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='ProvisionAguinaldo')
    ALTER TABLE [rrhh].[Nomina] ADD [ProvisionAguinaldo] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_ProvisionAguinaldo DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='ProvisionIndemnizacion')
    ALTER TABLE [rrhh].[Nomina] ADD [ProvisionIndemnizacion] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_ProvisionIndemnizacion DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='CostoTotalEmpresa')
    ALTER TABLE [rrhh].[Nomina] ADD [CostoTotalEmpresa] DECIMAL(18,2) NOT NULL CONSTRAINT DF_Nomina_CostoTotalEmpresa DEFAULT 0.00;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='PromedioAsistencia')
    ALTER TABLE [rrhh].[Nomina] ADD [PromedioAsistencia] DECIMAL(5,2) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rrhh' AND TABLE_NAME='Nomina' AND COLUMN_NAME='PromedioPuntualidad')
    ALTER TABLE [rrhh].[Nomina] ADD [PromedioPuntualidad] DECIMAL(5,2) NULL;
GO

-- 2. Tabla de Préstamos a Empleados
IF OBJECT_ID('rrhh.PrestamosEmpleados', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[PrestamosEmpleados] (
        [ID] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [EmpleadoID] INT NOT NULL REFERENCES [rrhh].[Empleados]([ID]),
        [MontoTotal] DECIMAL(18,2) NOT NULL,
        [CuotaMensual] DECIMAL(18,2) NOT NULL,
        [SaldoPendiente] DECIMAL(18,2) NOT NULL,
        [Motivo] NVARCHAR(255) NULL,
        [FechaInicio] DATE NOT NULL,
        [Estado] NVARCHAR(20) NOT NULL CONSTRAINT DF_PrestamosEmpleados_Estado DEFAULT 'Activo',
        [CreadoEn] DATETIME2 NOT NULL CONSTRAINT DF_PrestamosEmpleados_CreadoEn DEFAULT SYSUTCDATETIME(),
        [CreadoPor] INT NULL REFERENCES [seguridad].[Usuarios]([ID])
    );
END
GO

-- 3. Tabla de Cobros por Pérdidas
IF OBJECT_ID('rrhh.CobrosPerdidasEmpleados', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[CobrosPerdidasEmpleados] (
        [ID] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [EmpleadoID] INT NOT NULL REFERENCES [rrhh].[Empleados]([ID]),
        [Descripcion] NVARCHAR(255) NOT NULL,
        [MontoTotal] DECIMAL(18,2) NOT NULL,
        [SaldoPendiente] DECIMAL(18,2) NOT NULL,
        [NumeroDocumento] NVARCHAR(100) NULL,
        [FechaIncidente] DATE NOT NULL,
        [Estado] NVARCHAR(20) NOT NULL CONSTRAINT DF_CobrosPerdidas_Estado DEFAULT 'Pendiente',
        [CreadoEn] DATETIME2 NOT NULL CONSTRAINT DF_CobrosPerdidas_CreadoEn DEFAULT SYSUTCDATETIME(),
        [CreadoPor] INT NULL REFERENCES [seguridad].[Usuarios]([ID])
    );
END
GO

-- 4. Tabla de Propuestas y Plan de Vacaciones
IF OBJECT_ID('rrhh.PropuestasVacaciones', 'U') IS NULL
BEGIN
    CREATE TABLE [rrhh].[PropuestasVacaciones] (
        [ID] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [EmpleadoID] INT NOT NULL REFERENCES [rrhh].[Empleados]([ID]),
        [FechaInicio] DATE NOT NULL,
        [FechaFin] DATE NOT NULL,
        [Dias] INT NOT NULL,
        [Motivo] NVARCHAR(255) NULL CONSTRAINT DF_PropuestasVac_Motivo DEFAULT 'Plan Rotativo Semestral',
        [Estado] NVARCHAR(20) NOT NULL CONSTRAINT DF_PropuestasVac_Estado DEFAULT 'Propuesta',
        [CreadoEn] DATETIME2 NOT NULL CONSTRAINT DF_PropuestasVac_CreadoEn DEFAULT SYSUTCDATETIME(),
        [AprobadoPor] INT NULL REFERENCES [seguridad].[Usuarios]([ID]),
        [AprobadoEn] DATETIME2 NULL
    );
END
GO

-- ============================================================================
-- STORED PROCEDURES
-- ============================================================================

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarDetalleNomina]
    @NominaID INT,
    @Concepto VARCHAR(100),
    @Tipo VARCHAR(20),
    @Monto DECIMAL(18,2),
    @Descripcion VARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [rrhh].[DetalleNomina] (NominaID, Concepto, Tipo, Monto, Descripcion)
    VALUES (@NominaID, @Concepto, @Tipo, @Monto, @Descripcion);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerDetallesNomina]
    @NominaID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, NominaID, Concepto, Tipo, Monto, Descripcion
    FROM [rrhh].[DetalleNomina]
    WHERE NominaID = @NominaID
    ORDER BY CASE Tipo WHEN 'Ingreso' THEN 1 WHEN 'Deduccion' THEN 2 WHEN 'Patronal' THEN 3 ELSE 4 END, ID ASC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarPrestamosActivosEmpleado]
    @EmpleadoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, EmpleadoID, MontoTotal, CuotaMensual, SaldoPendiente, Motivo, FechaInicio, Estado
    FROM [rrhh].[PrestamosEmpleados]
    WHERE EmpleadoID = @EmpleadoID AND Estado = 'Activo' AND SaldoPendiente > 0;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_RegistrarAbonoPrestamo]
    @PrestamoID INT,
    @MontoAbono DECIMAL(18,2)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[PrestamosEmpleados]
    SET SaldoPendiente = CASE WHEN SaldoPendiente <= @MontoAbono THEN 0.00 ELSE SaldoPendiente - @MontoAbono END,
        Estado = CASE WHEN SaldoPendiente <= @MontoAbono THEN 'Pagado' ELSE 'Activo' END
    WHERE ID = @PrestamoID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarCobrosPerdidasPendientesEmpleado]
    @EmpleadoID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, EmpleadoID, Descripcion, MontoTotal, SaldoPendiente, NumeroDocumento, FechaIncidente, Estado
    FROM [rrhh].[CobrosPerdidasEmpleados]
    WHERE EmpleadoID = @EmpleadoID AND Estado = 'Pendiente' AND SaldoPendiente > 0;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_RegistrarCobroPerdida]
    @CobroID INT,
    @MontoDescontado DECIMAL(18,2)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[CobrosPerdidasEmpleados]
    SET SaldoPendiente = CASE WHEN SaldoPendiente <= @MontoDescontado THEN 0.00 ELSE SaldoPendiente - @MontoDescontado END,
        Estado = CASE WHEN SaldoPendiente <= @MontoDescontado THEN 'Descontado' ELSE 'Pendiente' END
    WHERE ID = @CobroID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_GuardarPropuestaVacaciones]
    @EmpleadoID INT,
    @FechaInicio DATE,
    @FechaFin DATE,
    @Dias INT,
    @Motivo NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [rrhh].[PropuestasVacaciones] (EmpleadoID, FechaInicio, FechaFin, Dias, Motivo, Estado)
    OUTPUT INSERTED.ID
    VALUES (@EmpleadoID, @FechaInicio, @FechaFin, @Dias, @Motivo, 'Propuesta');
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_AprobarPropuestaVacaciones]
    @PropuestaID INT,
    @AprobadoPor INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @EmpID INT, @Ini DATE, @Fin DATE, @Dias INT, @Motivo NVARCHAR(255);
    SELECT @EmpID = EmpleadoID, @Ini = FechaInicio, @Fin = FechaFin, @Dias = Dias, @Motivo = Motivo
    FROM [rrhh].[PropuestasVacaciones] WHERE ID = @PropuestaID;

    IF @EmpID IS NULL THROW 51055, 'Propuesta de vacaciones no encontrada.', 1;

    UPDATE [rrhh].[PropuestasVacaciones]
    SET Estado = 'Aprobada', AprobadoPor = @AprobadoPor, AprobadoEn = SYSUTCDATETIME()
    WHERE ID = @PropuestaID;

    INSERT INTO [rrhh].[LicenciasEmpleados] (EmpleadoID, TipoLicencia, FechaInicio, FechaFin, DiasOtorgados, PagoEmpleador, PagoINSS, Observaciones, AprobadoPor)
    VALUES (@EmpID, 'Vacaciones', @Ini, @Fin, @Dias, 100.00, 0.00, ISNULL(@Motivo, 'Plan de Vacaciones Aprobado'), @AprobadoPor);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarPropuestasVacaciones]
    @Anio INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.ID, p.EmpleadoID, e.NombreCompleto, e.Cargo, p.FechaInicio, p.FechaFin, p.Dias, p.Motivo, p.Estado, p.CreadoEn, p.AprobadoPor
    FROM [rrhh].[PropuestasVacaciones] p
    JOIN [rrhh].[Empleados] e ON p.EmpleadoID = e.ID
    WHERE (@Anio IS NULL OR YEAR(p.FechaInicio) = @Anio)
    ORDER BY p.FechaInicio ASC;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerHistoricoRentaAnualEmpleado]
    @EmpleadoID INT,
    @Anio INT,
    @MesLimite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ISNULL(SUM(TotalDevengado - INSSLaboral), 0) AS RentaGravableAcumulada,
        ISNULL(SUM(IRMensual), 0) AS IRRetenidoAcumulado,
        COUNT(*) AS MesesCalculados
    FROM [rrhh].[Nomina]
    WHERE EmpleadoID = @EmpleadoID
      AND YEAR(PeriodoFin) = @Anio
      AND MONTH(PeriodoFin) < @MesLimite
      AND Estado IN ('Contabilizada', 'Pagada');
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ActualizarNominaEstructurada]
    @NominaID INT,
    @Viaticos DECIMAL(18,2) = 0,
    @DepreciacionVehiculo DECIMAL(18,2) = 0,
    @Incentivos DECIMAL(18,2) = 0,
    @RiesgoLaboral DECIMAL(18,2) = 0,
    @SueldoExtraordinario DECIMAL(18,2) = 0,
    @PrestamosDescontados DECIMAL(18,2) = 0,
    @CobrosPerdidas DECIMAL(18,2) = 0,
    @ProvisionVacaciones DECIMAL(18,2) = 0,
    @ProvisionAguinaldo DECIMAL(18,2) = 0,
    @ProvisionIndemnizacion DECIMAL(18,2) = 0,
    @CostoTotalEmpresa DECIMAL(18,2) = 0,
    @PromedioAsistencia DECIMAL(5,2) = NULL,
    @PromedioPuntualidad DECIMAL(5,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [rrhh].[Nomina]
    SET Viaticos = @Viaticos,
        DepreciacionVehiculo = @DepreciacionVehiculo,
        Incentivos = @Incentivos,
        RiesgoLaboral = @RiesgoLaboral,
        SueldoExtraordinario = @SueldoExtraordinario,
        PrestamosDescontados = @PrestamosDescontados,
        CobrosPerdidas = @CobrosPerdidas,
        ProvisionVacaciones = @ProvisionVacaciones,
        ProvisionAguinaldo = @ProvisionAguinaldo,
        ProvisionIndemnizacion = @ProvisionIndemnizacion,
        CostoTotalEmpresa = @CostoTotalEmpresa,
        PromedioAsistencia = @PromedioAsistencia,
        PromedioPuntualidad = @PromedioPuntualidad
    WHERE ID = @NominaID;
END
GO

-- Permisos
GRANT EXECUTE ON SCHEMA::[rrhh] TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::[rrhh] TO [db_rol_gerencia];
GO


-- HR SPs extension
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerMetricasAsistenciaPeriodo]
    @EmpleadoID INT,
    @FechaInicio DATE,
    @FechaFin DATE
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        COUNT(*) AS TotalAsistencias,
        SUM(CASE WHEN EstadoEntrada IN ('A Tiempo', 'Puntual') THEN 1 ELSE 0 END) AS Puntuales,
        SUM(CASE WHEN EstadoEntrada IN ('Llegada Tardia', 'Tarde') THEN 1 ELSE 0 END) AS Tardanzas
    FROM [rrhh].[Asistencia]
    WHERE EmpleadoID = @EmpleadoID AND Fecha >= @FechaInicio AND Fecha <= @FechaFin;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerTotalVacacionesGozadasPorEmpleado]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT EmpleadoID, ISNULL(SUM(DiasOtorgados), 0) AS TotalGozadas
    FROM [rrhh].[LicenciasEmpleados]
    WHERE TipoLicencia = 'Vacaciones'
    GROUP BY EmpleadoID;
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarPrestamoEmpleado]
    @EmpleadoID INT,
    @MontoTotal DECIMAL(18,2),
    @CuotaMensual DECIMAL(18,2),
    @SaldoPendiente DECIMAL(18,2),
    @Motivo NVARCHAR(255),
    @FechaInicio DATE,
    @CreadoPor INT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [rrhh].[PrestamosEmpleados] (EmpleadoID, MontoTotal, CuotaMensual, SaldoPendiente, Motivo, FechaInicio, Estado, CreadoPor)
    OUTPUT INSERTED.ID
    VALUES (@EmpleadoID, @MontoTotal, @CuotaMensual, @SaldoPendiente, @Motivo, @FechaInicio, 'Activo', @CreadoPor);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_InsertarCobroPerdidaEmpleado]
    @EmpleadoID INT,
    @Descripcion NVARCHAR(255),
    @MontoTotal DECIMAL(18,2),
    @SaldoPendiente DECIMAL(18,2),
    @CuotaMensual DECIMAL(18,2) = NULL,
    @NumeroDocumento NVARCHAR(100) = NULL,
    @FechaIncidente DATE,
    @CreadoPor INT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [rrhh].[CobrosPerdidasEmpleados] (EmpleadoID, Descripcion, MontoTotal, SaldoPendiente, NumeroDocumento, FechaIncidente, Estado, CreadoPor)
    OUTPUT INSERTED.ID
    VALUES (@EmpleadoID, @Descripcion, @MontoTotal, @SaldoPendiente, @NumeroDocumento, @FechaIncidente, 'Pendiente', @CreadoPor);
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarTodosPrestamosActivos]
    @EmpleadoID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.ID, p.EmpleadoID, e.NombreCompleto, p.MontoTotal, p.CuotaMensual, p.SaldoPendiente, p.Motivo, p.FechaInicio, p.Estado
    FROM [rrhh].[PrestamosEmpleados] p
    JOIN [rrhh].[Empleados] e ON p.EmpleadoID = e.ID
    WHERE (@EmpleadoID IS NULL OR p.EmpleadoID = @EmpleadoID) AND p.Estado = 'Activo';
END
GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarTodosCobrosPerdidasPendientes]
    @EmpleadoID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT c.ID, c.EmpleadoID, e.NombreCompleto, c.Descripcion, c.MontoTotal, c.SaldoPendiente, c.NumeroDocumento, c.FechaIncidente, c.Estado
    FROM [rrhh].[CobrosPerdidasEmpleados] c
    JOIN [rrhh].[Empleados] e ON c.EmpleadoID = e.ID
    WHERE (@EmpleadoID IS NULL OR c.EmpleadoID = @EmpleadoID) AND c.Estado = 'Pendiente';
END
GO

GRANT EXECUTE ON [rrhh].[sp_ObtenerMetricasAsistenciaPeriodo] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_ObtenerMetricasAsistenciaPeriodo] TO [db_rol_gerencia];
GRANT EXECUTE ON [rrhh].[sp_ObtenerTotalVacacionesGozadasPorEmpleado] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_ObtenerTotalVacacionesGozadasPorEmpleado] TO [db_rol_gerencia];
GRANT EXECUTE ON [rrhh].[sp_InsertarPrestamoEmpleado] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_InsertarPrestamoEmpleado] TO [db_rol_gerencia];
GRANT EXECUTE ON [rrhh].[sp_InsertarCobroPerdidaEmpleado] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_InsertarCobroPerdidaEmpleado] TO [db_rol_gerencia];
GRANT EXECUTE ON [rrhh].[sp_ListarTodosPrestamosActivos] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_ListarTodosPrestamosActivos] TO [db_rol_gerencia];
GRANT EXECUTE ON [rrhh].[sp_ListarTodosCobrosPerdidasPendientes] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_ListarTodosCobrosPerdidasPendientes] TO [db_rol_gerencia];
GO

GRANT EXECUTE ON SCHEMA::rrhh TO [db_rol_superadmin];
GRANT EXECUTE ON SCHEMA::rrhh TO [db_rol_gerencia];
GRANT SELECT ON SCHEMA::rrhh TO [db_rol_superadmin];
GRANT SELECT ON SCHEMA::rrhh TO [db_rol_gerencia];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[PropuestasVacaciones] TO [db_rol_superadmin];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[PropuestasVacaciones] TO [db_rol_gerencia];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[PrestamosEmpleados] TO [db_rol_superadmin];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[PrestamosEmpleados] TO [db_rol_gerencia];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[CobrosPerdidasEmpleados] TO [db_rol_superadmin];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[CobrosPerdidasEmpleados] TO [db_rol_gerencia];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[DetalleNomina] TO [db_rol_superadmin];
GRANT INSERT, UPDATE, DELETE ON OBJECT::[rrhh].[DetalleNomina] TO [db_rol_gerencia];
GO

GO

CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerAsistenciaConTurnoPorEmpleadoRango]
    @EmpleadoID INT,
    @FechaInicio DATE,
    @FechaFin DATE
AS
BEGIN
    SET NOCOUNT ON;
    SELECT a.Fecha, a.HoraEntrada, a.HoraSalida, a.EstadoEntrada,
           t.HoraEntrada AS TurnoEntrada, t.HoraSalida AS TurnoSalida
    FROM [rrhh].[Asistencia] a
    LEFT JOIN [rrhh].[TurnosLaborales] t ON a.TurnoID = t.ID
    WHERE a.EmpleadoID = @EmpleadoID AND a.Fecha >= @FechaInicio AND a.Fecha <= @FechaFin
    ORDER BY a.Fecha ASC;
END

GO
GRANT EXECUTE ON [rrhh].[sp_ObtenerAsistenciaConTurnoPorEmpleadoRango] TO [db_rol_superadmin];
GRANT EXECUTE ON [rrhh].[sp_ObtenerAsistenciaConTurnoPorEmpleadoRango] TO [db_rol_gerencia];
GO
