-- Reparacion acotada de contratos SQL de inventario (06-11-2026).
-- Preparado para revision; NO aplicado. No se ejecuta durante el despliegue Azure.
-- Ejecutar primero en QA y en una unica transaccion administrada por el cliente,
-- abortando y revirtiendo toda la transaccion ante cualquier error de un lote GO.
-- Definiciones copiadas de la ultima version de cada SP en 03_stored_procedures.sql.
-- No elimina tablas, registros, permisos ni actualiza movimientos existentes.
SET XACT_ABORT ON;
GO

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
