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
