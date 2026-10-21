/* Durable SMTP outbox. Apply after 03_stored_procedures.sql.
   No log contents are rewritten. Accepted SMTP + lost ACK can redeliver.
   Reservations are serialized only during short SQL transactions, never SMTP I/O.
   Run the consumer with db_rol_alertas_worker; never grant broad seguridad access. */
SET NOCOUNT ON;
GO
IF OBJECT_ID(N'seguridad.AlertasSMTPOutbox', N'U') IS NULL
BEGIN
    CREATE TABLE seguridad.AlertasSMTPOutbox (
        ErrorID BIGINT NOT NULL CONSTRAINT PK_AlertasSMTPOutbox PRIMARY KEY,
        DedupKey BINARY(32) NOT NULL,
        Estado VARCHAR(12) NOT NULL CONSTRAINT DF_AlertasSMTP_Estado DEFAULT 'Pending',
        DisponibleDesde DATETIME2(3) NOT NULL CONSTRAINT DF_AlertasSMTP_Disponible DEFAULT SYSUTCDATETIME(),
        ClaimToken UNIQUEIDENTIFIER NULL,
        LeaseHasta DATETIME2(3) NULL,
        Intentos INT NOT NULL CONSTRAINT DF_AlertasSMTP_Intentos DEFAULT 0,
        DestinatariosJSON NVARCHAR(MAX) NULL,
        Forzar BIT NOT NULL CONSTRAINT DF_AlertasSMTP_Forzar DEFAULT 0,
        CONSTRAINT FK_AlertasSMTP_Error FOREIGN KEY (ErrorID) REFERENCES seguridad.BitacoraErrores(ID),
        CONSTRAINT CK_AlertasSMTP_Estado CHECK (Estado IN ('Pending', 'Sending', 'Sent', 'Suppressed')),
        CONSTRAINT CK_AlertasSMTP_JSON CHECK (DestinatariosJSON IS NULL OR ISJSON(DestinatariosJSON)=1)
    );
    CREATE INDEX IX_AlertasSMTP_Consumir ON seguridad.AlertasSMTPOutbox(Estado, DisponibleDesde, ErrorID)
        INCLUDE(DedupKey, LeaseHasta, Forzar);
END;
IF OBJECT_ID(N'seguridad.AlertasSMTPDedup', N'U') IS NULL
    CREATE TABLE seguridad.AlertasSMTPDedup (
        DedupKey BINARY(32) NOT NULL CONSTRAINT PK_AlertasSMTPDedup PRIMARY KEY,
        UltimoEnvio DATETIME2(3) NULL,
        ClaimToken UNIQUEIDENTIFIER NULL,
        LeaseHasta DATETIME2(3) NULL
    );
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'seguridad.BitacoraErrores')
               AND name=N'IX_BitacoraErrores_SMTPPendiente')
    CREATE INDEX IX_BitacoraErrores_SMTPPendiente ON seguridad.BitacoraErrores(ID) WHERE NotificadoSMTP=0;
IF DATABASE_PRINCIPAL_ID(N'db_rol_alertas_worker') IS NULL
    CREATE ROLE db_rol_alertas_worker AUTHORIZATION dbo;
GO
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
