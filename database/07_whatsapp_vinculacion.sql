-- Aditiva e idempotente; requiere 06_whatsapp_bot.sql. Aplicar primero en QA.
SET XACT_ABORT ON;
GO
IF OBJECT_ID('crm.WhatsAppControl') IS NULL THROW 52027,'Instale primero la migración 06 de WhatsApp.',1;
IF COL_LENGTH('crm.WhatsAppControl','ConnectionRevision') IS NULL
 ALTER TABLE crm.WhatsAppControl ADD ConnectionRevision INT NOT NULL CONSTRAINT DF_WA_ConnectionRevision DEFAULT 0,
  Vinculado BIT NOT NULL CONSTRAINT DF_WA_Vinculado DEFAULT 0, CuentaTelefono VARCHAR(20) NULL,
  SolicitudID VARCHAR(32) NULL, SolicitudAccion VARCHAR(12) NULL, SolicitudEstado VARCHAR(12) NULL,
  SolicitudError NVARCHAR(250) NULL, SolicitadoPor INT NULL, SolicitadoEn DATETIME2 NULL;
IF OBJECT_ID('crm.WhatsAppVinculosAudit') IS NULL
 CREATE TABLE crm.WhatsAppVinculosAudit(
  ID BIGINT IDENTITY PRIMARY KEY, SolicitudID VARCHAR(32) NULL, ActorID INT NULL,
  Accion VARCHAR(20) NOT NULL, Resultado VARCHAR(12) NOT NULL,
  Creado DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
IF COL_LENGTH('crm.WhatsAppVinculosAudit','DatosSesion') IS NULL
 ALTER TABLE crm.WhatsAppVinculosAudit ADD DatosSesion NVARCHAR(MAX) NULL;
IF OBJECT_ID('crm.WhatsAppAuthIntentos') IS NULL
 CREATE TABLE crm.WhatsAppAuthIntentos(ActorID INT PRIMARY KEY, Inicio DATETIME2 NOT NULL, Intentos INT NOT NULL);
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppIntentoAdmin
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 DECLARE @Actor INT=TRY_CONVERT(INT,SESSION_CONTEXT(N'usuario_id'));
 IF @Actor IS NULL OR COALESCE(CONVERT(NVARCHAR(30),SESSION_CONTEXT(N'rol')),'') NOT IN ('Admin','SuperAdmin')
  THROW 52027,'Se requiere una sesión administrativa.',1;
 BEGIN TRANSACTION;
 IF NOT EXISTS(SELECT 1 FROM crm.WhatsAppAuthIntentos WITH(UPDLOCK,HOLDLOCK) WHERE ActorID=@Actor)
  INSERT crm.WhatsAppAuthIntentos VALUES(@Actor,SYSUTCDATETIME(),0);
 UPDATE crm.WhatsAppAuthIntentos SET Intentos=0,Inicio=SYSUTCDATETIME()
  WHERE ActorID=@Actor AND Inicio<=DATEADD(minute,-15,SYSUTCDATETIME());
 DECLARE @Permitido BIT=0;
 UPDATE crm.WhatsAppAuthIntentos SET Intentos=Intentos+1 WHERE ActorID=@Actor AND Intentos<5;
 IF @@ROWCOUNT=1 SET @Permitido=1;
 COMMIT;
 SELECT @Permitido;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppResultadoAuth @Exitoso BIT
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @Actor INT=TRY_CONVERT(INT,SESSION_CONTEXT(N'usuario_id'));
 IF @Actor IS NULL OR COALESCE(CONVERT(NVARCHAR(30),SESSION_CONTEXT(N'rol')),'') NOT IN ('Admin','SuperAdmin')
  THROW 52027,'Se requiere una sesión administrativa.',1;
 IF @Exitoso=1 UPDATE crm.WhatsAppAuthIntentos SET Intentos=0,Inicio=SYSUTCDATETIME() WHERE ActorID=@Actor;
 INSERT crm.WhatsAppVinculosAudit(ActorID,Accion,Resultado) VALUES(@Actor,'REAUTENTICAR',CASE WHEN @Exitoso=1 THEN 'Correcta' ELSE 'Rechazada' END);
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppSolicitarVinculo @Accion VARCHAR(12), @Revision INT, @Solicitud VARCHAR(32)
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 DECLARE @Actor INT=TRY_CONVERT(INT,SESSION_CONTEXT(N'usuario_id'));
 IF @Actor IS NULL OR COALESCE(CONVERT(NVARCHAR(30),SESSION_CONTEXT(N'rol')),'') NOT IN ('Admin','SuperAdmin')
  THROW 52027,'Se requiere una sesión administrativa.',1;
 IF @Accion NOT IN ('VINCULAR','DESVINCULAR') OR @Accion IS NULL OR @Revision IS NULL OR @Solicitud IS NULL OR LEN(@Solicitud)<>32
  THROW 52027,'Solicitud de cuenta no válida.',1;
 BEGIN TRANSACTION;
 DECLARE @Actual INT,@Pendiente VARCHAR(12),@Estado VARCHAR(12),@TieneQRValido BIT=0,@WorkerVivo BIT=0,@DesvincularExpirado BIT=0;
 SELECT @Actual=ConnectionRevision,@Pendiente=SolicitudAccion,@Estado=SolicitudEstado,
  @WorkerVivo=CASE WHEN Heartbeat>DATEADD(second,-30,SYSUTCDATETIME()) THEN 1 ELSE 0 END,
  @DesvincularExpirado=CASE WHEN SolicitudEnCurso=1 AND (Heartbeat IS NULL OR Heartbeat<DATEADD(second,-25,SYSUTCDATETIME()) OR SolicitadoEn<DATEADD(second,-20,SYSUTCDATETIME())) THEN 1 ELSE 0 END,
  @TieneQRValido=CASE WHEN @Accion='VINCULAR' AND Vinculado=0
   AND QR IS NOT NULL AND QRExpira>DATEADD(second,35,SYSUTCDATETIME())
   AND Heartbeat>DATEADD(second,-15,SYSUTCDATETIME()) THEN 1 ELSE 0 END
  FROM (
   SELECT *, CASE WHEN SolicitudEstado='Pendiente' AND SolicitudAccion='DESVINCULAR' THEN 1 ELSE 0 END AS SolicitudEnCurso
   FROM crm.WhatsAppControl WITH(UPDLOCK,HOLDLOCK) WHERE ID=1
  ) c;
 IF @Revision<>@Actual THROW 52027,'La conexión cambió. Actualice el panel.',1;
 IF @Estado='Pendiente' AND @Pendiente='DESVINCULAR' AND @Accion='DESVINCULAR' AND @DesvincularExpirado=0
 BEGIN
  COMMIT; SELECT * FROM crm.WhatsAppControl WHERE ID=1; RETURN;
 END;
 IF @Estado='Pendiente' AND @Pendiente='DESVINCULAR' AND @DesvincularExpirado=1
 BEGIN
  DELETE FROM crm.WhatsAppVinculosAudit WHERE Accion='SESION_BACKUP';
  UPDATE crm.WhatsAppControl SET Vinculado=0,CuentaTelefono=NULL,QR=NULL,QRExpira=NULL,
   Estado=N'Sin vincular',Activo=0,SolicitudEstado='Completada',SolicitudError=NULL WHERE ID=1;
  UPDATE crm.WhatsAppSesiones SET Revision=Revision+1,Pendiente=NULL,Avisos=0,Imagen=NULL;
  UPDATE crm.WhatsAppInbox SET Estado='Procesado' WHERE Estado='Pendiente';
  UPDATE crm.WhatsAppOutbox SET Estado='Cancelado' WHERE Estado='Pendiente';
  IF @Accion='DESVINCULAR'
  BEGIN
   COMMIT; SELECT * FROM crm.WhatsAppControl WHERE ID=1; RETURN;
  END;
  SET @Estado='Completada';
 END;
 IF @Estado='Pendiente' AND @Pendiente='DESVINCULAR'
  THROW 52027,'Espere a que termine la desvinculación antes de vincular otra cuenta.',1;
 IF @TieneQRValido=1
  UPDATE crm.WhatsAppControl SET ConnectionRevision=ConnectionRevision+1,
   SolicitudID=@Solicitud,SolicitudAccion='VINCULAR',SolicitudEstado='Pendiente',
   SolicitudError=NULL,SolicitadoPor=@Actor,SolicitadoEn=SYSUTCDATETIME(),Activo=0 WHERE ID=1;
 ELSE
  UPDATE crm.WhatsAppControl SET ConnectionRevision=ConnectionRevision+1, SolicitudID=@Solicitud,
   SolicitudAccion=@Accion,SolicitudEstado='Pendiente',SolicitudError=NULL,SolicitadoPor=@Actor,
   SolicitadoEn=SYSUTCDATETIME(),Activo=0,QR=NULL,QRExpira=NULL WHERE ID=1;
 IF @Accion='DESVINCULAR'
 BEGIN
  UPDATE crm.WhatsAppSesiones SET Revision=Revision+1,Pendiente=NULL;
  UPDATE crm.WhatsAppOutbox SET Estado='Cancelado' WHERE Estado='Pendiente';
 END;
 INSERT crm.WhatsAppVinculosAudit(SolicitudID,ActorID,Accion,Resultado) VALUES(@Solicitud,@Actor,@Accion,'Pendiente');
 COMMIT;
 SELECT * FROM crm.WhatsAppControl WHERE ID=1;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCompletarVinculo @Solicitud VARCHAR(32),@Exitoso BIT,@Error NVARCHAR(250)=NULL
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRANSACTION;
 DECLARE @Accion VARCHAR(12),@Actor INT;
 SELECT @Accion=SolicitudAccion,@Actor=SolicitadoPor FROM crm.WhatsAppControl WITH(UPDLOCK,HOLDLOCK)
  WHERE ID=1 AND SolicitudID=@Solicitud AND SolicitudEstado='Pendiente';
 IF @Accion IS NULL BEGIN COMMIT; RETURN; END;
 IF @Exitoso=1 AND @Accion='VINCULAR' AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppControl WHERE ID=1 AND Vinculado=1)
 BEGIN COMMIT; RETURN; END;
 IF @Exitoso=1 AND @Accion='DESVINCULAR'
 BEGIN
  DELETE FROM crm.WhatsAppVinculosAudit WHERE Accion='SESION_BACKUP';
  UPDATE crm.WhatsAppControl SET Vinculado=0,CuentaTelefono=NULL,QR=NULL,QRExpira=NULL,
   Estado=N'Sin vincular',Activo=0 WHERE ID=1;
  -- Retain orders/history; never carry drafts, queued sends or consent to another account.
  UPDATE crm.WhatsAppSesiones SET Revision=Revision+1,Pendiente=NULL,Avisos=0,Imagen=NULL;
  UPDATE crm.WhatsAppInbox SET Estado='Procesado' WHERE Estado='Pendiente';
  UPDATE crm.WhatsAppOutbox SET Estado='Cancelado' WHERE Estado='Pendiente';
 END;
 UPDATE crm.WhatsAppControl SET SolicitudEstado=CASE WHEN @Exitoso=1 THEN 'Completada' ELSE 'Error' END,
  SolicitudError=CASE WHEN @Exitoso=1 THEN NULL ELSE @Error END WHERE ID=1;
 INSERT crm.WhatsAppVinculosAudit(SolicitudID,ActorID,Accion,Resultado)
  VALUES(@Solicitud,@Actor,@Accion,CASE WHEN @Exitoso=1 THEN 'Completada' ELSE 'Error' END);
 COMMIT;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCuenta @Telefono VARCHAR(20),@Vinculado BIT
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRANSACTION;
 IF @Vinculado=0
 BEGIN
  DELETE FROM crm.WhatsAppVinculosAudit WHERE Accion='SESION_BACKUP';
  UPDATE crm.WhatsAppControl WITH(UPDLOCK,HOLDLOCK) SET Activo=0,ConnectionRevision=ConnectionRevision+1 WHERE ID=1;
  UPDATE crm.WhatsAppSesiones SET Revision=Revision+1,Pendiente=NULL,Avisos=0,Imagen=NULL;
  UPDATE crm.WhatsAppInbox SET Estado='Procesado' WHERE Estado='Pendiente';
  UPDATE crm.WhatsAppOutbox SET Estado='Cancelado' WHERE Estado='Pendiente';
 END;
 UPDATE crm.WhatsAppControl SET CuentaTelefono=@Telefono,Vinculado=@Vinculado,QR=NULL,QRExpira=NULL WHERE ID=1;
 COMMIT;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppGuardarSesion @Datos NVARCHAR(MAX)
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRANSACTION;
 DELETE FROM crm.WhatsAppVinculosAudit WHERE Accion='SESION_BACKUP';
 IF @Datos IS NOT NULL AND LEN(@Datos)>0
  INSERT crm.WhatsAppVinculosAudit(Accion,Resultado,DatosSesion) VALUES('SESION_BACKUP','Activa',@Datos);
 COMMIT;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppLeerSesion
AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 1 DatosSesion FROM crm.WhatsAppVinculosAudit WHERE Accion='SESION_BACKUP' AND DatosSesion IS NOT NULL ORDER BY ID DESC;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppLeerConfigIA
AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 1 DatosSesion FROM crm.WhatsAppVinculosAudit WHERE Accion='CONFIG_IA' AND DatosSesion IS NOT NULL ORDER BY ID DESC;
END;
GO
CREATE OR ALTER PROCEDURE crm.sp_ObtenerCotizacionesPendientesAdmin
AS
BEGIN
 SET NOCOUNT ON;
 SELECT c.*,cl.Nombre AS ClienteNombre,
  CASE WHEN EXISTS(SELECT 1 FROM crm.WhatsAppSesiones s WHERE s.Token=c.SessionID)
   THEN 'WhatsApp' ELSE 'Web' END AS CanalOrigen
 FROM crm.Cotizaciones c LEFT JOIN crm.Clientes cl ON c.ClienteID=cl.ID
 WHERE c.Estado IN ('Pendiente','Cotizada','Aceptada')
 ORDER BY CASE WHEN c.Estado='Pendiente' THEN 0 ELSE 1 END,c.FechaSolicitud ASC;
END;
GO
-- Linking remains possible while automatic attention is paused. Do not resume old sends.
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppActivar @P1 BIT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF @P1=1 AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppControl WHERE ID=1 AND Vinculado=1 AND Estado=N'Conectado'
    AND Heartbeat>DATEADD(second,-30,SYSUTCDATETIME())
    AND NOT (COALESCE(SolicitudAccion,'')='DESVINCULAR' AND COALESCE(SolicitudEstado,'')='Pendiente'))
  THROW 52027,'Vincule la cuenta y espere a que esté conectada antes de activar los envíos.',1;
 UPDATE crm.WhatsAppControl SET Activo=@P1 WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppIntentoAdmin TO db_rol_gerencia,db_rol_superadmin;
GRANT EXECUTE ON crm.sp_WhatsAppResultadoAuth TO db_rol_gerencia,db_rol_superadmin;
GRANT EXECUTE ON crm.sp_WhatsAppSolicitarVinculo TO db_rol_gerencia,db_rol_superadmin;
GRANT EXECUTE ON crm.sp_WhatsAppCompletarVinculo TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
GRANT EXECUTE ON crm.sp_WhatsAppCuenta TO usr_bd_whatsapp;
GRANT EXECUTE ON crm.sp_WhatsAppGuardarSesion TO usr_bd_whatsapp;
GRANT EXECUTE ON crm.sp_WhatsAppLeerSesion TO usr_bd_whatsapp;
GRANT EXECUTE ON crm.sp_WhatsAppLeerConfigIA TO usr_bd_whatsapp;
GRANT EXECUTE ON crm.sp_WhatsAppModo TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
GRANT EXECUTE ON crm.sp_WhatsAppActivar TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
DENY EXECUTE ON crm.sp_WhatsAppIntentoAdmin TO usr_bd_whatsapp,db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppResultadoAuth TO usr_bd_whatsapp,db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppSolicitarVinculo TO usr_bd_whatsapp,db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppCompletarVinculo TO db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppCuenta TO db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppGuardarSesion TO db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppLeerSesion TO db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
DENY EXECUTE ON crm.sp_WhatsAppLeerConfigIA TO db_rol_cajero_pos,db_rol_produccion,db_rol_kiosco,db_rol_portal_cliente;
GO
