-- Aditiva e idempotente. Ejecutar primero en QA; requiere los ocho esquemas existentes.
SET XACT_ABORT ON;
GO
IF OBJECT_ID('crm.WhatsAppControl') IS NULL
BEGIN
 CREATE TABLE crm.WhatsAppControl (
  ID INT NOT NULL PRIMARY KEY CHECK(ID=1), Activo BIT NOT NULL DEFAULT 0,
  Estado NVARCHAR(40) NOT NULL DEFAULT N'Desconectado', QR NVARCHAR(MAX) NULL,
  Heartbeat DATETIME2 NULL, QRExpira DATETIME2 NULL);
 INSERT crm.WhatsAppControl(ID) VALUES(1);
END;
IF OBJECT_ID('crm.WhatsAppSesiones') IS NULL
 CREATE TABLE crm.WhatsAppSesiones (
  ID INT IDENTITY PRIMARY KEY, JID VARCHAR(100) NOT NULL UNIQUE,
  Telefono VARCHAR(20) NOT NULL, Token VARCHAR(100) NOT NULL UNIQUE,
  Modo VARCHAR(6) NOT NULL DEFAULT 'IA' CHECK(Modo IN ('IA','HUMANO')),
  Revision INT NOT NULL DEFAULT 0, Avisos BIT NOT NULL DEFAULT 0,
  Pendiente NVARCHAR(MAX) NULL, Imagen VARCHAR(255) NULL,
  UltimaInteraccion DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
IF OBJECT_ID('crm.WhatsAppInbox') IS NULL
 CREATE TABLE crm.WhatsAppInbox (
  ID BIGINT IDENTITY PRIMARY KEY, SesionID INT NOT NULL REFERENCES crm.WhatsAppSesiones(ID),
  MessageID VARCHAR(200) NOT NULL, Texto NVARCHAR(4000) NOT NULL, Imagen VARCHAR(255) NULL,
  Estado VARCHAR(10) NOT NULL DEFAULT 'Pendiente', Intentos INT NOT NULL DEFAULT 0,
  Creado DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  UNIQUE(SesionID,MessageID));
IF OBJECT_ID('crm.WhatsAppOutbox') IS NULL
 CREATE TABLE crm.WhatsAppOutbox (
  ID BIGINT IDENTITY PRIMARY KEY, SesionID INT NOT NULL REFERENCES crm.WhatsAppSesiones(ID),
  Clave VARCHAR(200) NOT NULL UNIQUE, Texto NVARCHAR(4000) NOT NULL,
  Tipo VARCHAR(10) NOT NULL DEFAULT 'IA', Revision INT NOT NULL,
  Estado VARCHAR(10) NOT NULL DEFAULT 'Pendiente', Intentos INT NOT NULL DEFAULT 0,
  Disponible DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  Creado DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
IF OBJECT_ID('crm.WhatsAppAcciones') IS NULL
 CREATE TABLE crm.WhatsAppAcciones (
  Clave VARCHAR(200) PRIMARY KEY, SesionID INT NOT NULL REFERENCES crm.WhatsAppSesiones(ID),
  Herramienta VARCHAR(80) NOT NULL, Resultado NVARCHAR(MAX) NOT NULL,
  Creado DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
GO
-- The worker has its own contained principal; never grants on invoices/payments/HR.
IF DATABASE_PRINCIPAL_ID('usr_bd_whatsapp') IS NULL CREATE USER usr_bd_whatsapp WITHOUT LOGIN;
GRANT IMPERSONATE ON USER::usr_bd_portal_cliente TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCotizacion
 @Sesion INT, @Operacion VARCHAR(12), @Cotizacion INT=NULL,
 @Nombre NVARCHAR(100)=NULL, @Detalle NVARCHAR(MAX)=NULL, @Fecha DATETIME2=NULL,
 @PrecioEsperado DECIMAL(18,2)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON;
 -- Ownership chaining permits narrowly scoped channel operations, no direct table grants.
 DECLARE @Token VARCHAR(100), @Telefono VARCHAR(20), @Imagen VARCHAR(255);
 SELECT @Token=Token,@Telefono=Telefono,@Imagen=Imagen FROM crm.WhatsAppSesiones WHERE ID=@Sesion;
 IF @Token IS NULL THROW 52026,'Sesión WhatsApp inexistente.',1;
 IF @Operacion='listar'
 BEGIN
  SELECT TOP 20 ID,Especificaciones,FechaEntrega,Estado,PrecioCotizado FROM crm.Cotizaciones
   WHERE ClienteID IS NULL AND SessionID=@Token ORDER BY ID DESC;
  RETURN;
 END;
 IF NOT EXISTS(SELECT 1 FROM crm.WhatsAppControl WHERE ID=1 AND Activo=1)
  OR NOT EXISTS(SELECT 1 FROM crm.WhatsAppSesiones WHERE ID=@Sesion AND Modo='IA')
  THROW 52026,'Bot pausado.',1;
 IF @Operacion='crear'
 BEGIN
  IF @Fecha < DATEADD(hour,24,DATEADD(hour,-6,SYSUTCDATETIME())) OR @Fecha IS NULL
   THROW 52026,'Se requieren 24 horas de anticipación.',1;
  IF (SELECT COUNT(*) FROM crm.Cotizaciones WITH(UPDLOCK,HOLDLOCK)
      WHERE SessionID=@Token AND Estado IN ('Pendiente','Cotizada')) >= 3
   THROW 52026,'Ya hay tres cotizaciones abiertas.',1;
  INSERT crm.Cotizaciones(ClienteID,SessionID,Especificaciones,FechaEntrega,RutaImagenReferencia,TelefonoContacto,NombreContacto,Estado)
   OUTPUT INSERTED.ID VALUES(NULL,@Token,@Detalle,@Fecha,@Imagen,@Telefono,@Nombre,'Pendiente');
  RETURN;
 END;
 IF @Operacion NOT IN ('aceptar','rechazar') THROW 52026,'Operación no permitida.',1;
 UPDATE crm.Cotizaciones WITH(UPDLOCK,HOLDLOCK)
  SET Estado=CASE WHEN @Operacion='aceptar' THEN 'Aceptada' ELSE 'Rechazada' END
  WHERE ID=@Cotizacion AND ClienteID IS NULL AND SessionID=@Token AND Estado='Cotizada'
   AND PrecioCotizado=@PrecioEsperado;
 IF @@ROWCOUNT<>1 THROW 52026,'Cotización ajena, inexistente o ya procesada.',1;
 SELECT @Cotizacion AS ID;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCotizacion TO usr_bd_whatsapp;
GO
-- Called inside the POS/KDS transaction. No migration => hooks are disabled in Python.
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppNotificar
 @Tipo VARCHAR(12), @ID INT
AS
BEGIN
 SET NOCOUNT ON;
 IF NOT EXISTS(SELECT 1 FROM crm.WhatsAppControl WHERE Activo=1) RETURN;
 DECLARE @Texto NVARCHAR(4000), @Clave VARCHAR(200), @Sesion INT;
 IF @Tipo='cotizacion'
 BEGIN
  SELECT @Sesion=s.ID,
   @Texto=CONCAT(N'Tu cotización COT-',c.ID,N' está lista: C$ ',c.PrecioCotizado,
    N'. Indica el código y si deseas aceptarla o rechazarla.'),
   @Clave=CONCAT('quote:',c.ID,':',c.PrecioCotizado)
  FROM crm.Cotizaciones c JOIN crm.WhatsAppSesiones s ON c.SessionID=s.Token
  WHERE c.ID=@ID AND c.ClienteID IS NULL AND c.Estado='Cotizada' AND s.Avisos=1;
 END
 ELSE IF @Tipo='pedido'
 BEGIN
  -- Proactive orders require explicit opt-in. No access to history is conferred.
  SELECT @Sesion=s.ID,@Texto=CONCAT(N'Tu pedido ',f.NumeroFactura,N' está ',e.Estado,
   N'. Consulta el saldo con tu código privado de seguimiento.'),
   @Clave=CONCAT('order:',f.ID,':',e.Estado)
  FROM ventas.Encargos e JOIN ventas.Facturas f ON f.ID=e.FacturaID
  JOIN crm.WhatsAppSesiones s ON RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(e.TelefonoContacto,'+',''),'-',''),' ',''),'.',''),8)=RIGHT(s.Telefono,8)
  WHERE f.ID=@ID AND f.EstadoFiscal='Emitida' AND e.Estado IN ('En Proceso','Listo') AND s.Avisos=1;
 END;
 IF @Sesion IS NOT NULL AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppOutbox WITH(UPDLOCK,HOLDLOCK) WHERE Clave=@Clave)
  INSERT crm.WhatsAppOutbox(SesionID,Clave,Texto,Tipo,Revision)
   SELECT ID,@Clave,@Texto,'Aviso',Revision FROM crm.WhatsAppSesiones WHERE ID=@Sesion;
END;
GO
REVOKE EXECUTE ON SCHEMA::[crm] FROM [db_rol_produccion]; GRANT EXECUTE ON crm.sp_WhatsAppNotificar TO db_rol_cajero_pos,db_rol_gerencia,db_rol_superadmin,db_rol_produccion;
GO

-- Channel persistence API: typed procedures preserve the no-direct-SQL boundary.
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppEncolar
 @P1 VARCHAR(200)=NULL,
 @P2 INT=NULL,
 @P3 VARCHAR(200)=NULL,
 @P4 NVARCHAR(4000)=NULL,
 @P5 VARCHAR(10)=NULL,
 @P6 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF NOT EXISTS(SELECT 1 FROM crm.WhatsAppOutbox WITH(UPDLOCK,HOLDLOCK) WHERE Clave=@P1) INSERT crm.WhatsAppOutbox(SesionID,Clave,Texto,Tipo,Revision) VALUES(@P2,@P3,@P4,@P5,@P6);
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppEncolar TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppLeerControl

AS
BEGIN
 SET NOCOUNT ON;
 SELECT * FROM crm.WhatsAppControl WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppLeerControl TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBuscarSesion
 @P1 VARCHAR(100)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT ID FROM crm.WhatsAppSesiones WITH(UPDLOCK,HOLDLOCK) WHERE JID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBuscarSesion TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBuscarMensaje
 @P1 INT=NULL,
 @P2 VARCHAR(200)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT ID FROM crm.WhatsAppInbox WITH(UPDLOCK,HOLDLOCK) WHERE SesionID=@P1 AND MessageID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBuscarMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppContarRecientes
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT COUNT(*) FROM crm.WhatsAppInbox WHERE SesionID=@P1 AND Creado>DATEADD(minute,-1,SYSUTCDATETIME());
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppContarRecientes TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppInsertarMensaje
 @P1 INT=NULL,
 @P2 VARCHAR(200)=NULL,
 @P3 NVARCHAR(4000)=NULL,
 @P4 VARCHAR(255)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 INSERT crm.WhatsAppInbox(SesionID,MessageID,Texto,Imagen) VALUES(@P1,@P2,@P3,@P4);
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppInsertarMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppActualizarImagen
 @P1 VARCHAR(255)=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET UltimaInteraccion=SYSUTCDATETIME(),Imagen=COALESCE(@P1,Imagen) WHERE ID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppActualizarImagen TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppMarcarFallidos

AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppInbox SET Estado='Fallido' WHERE Estado='Pendiente' AND Intentos>=3;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppMarcarFallidos TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppSiguienteMensaje

AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 1 i.ID,i.Texto,i.MessageID,i.Imagen,s.ID AS id,s.Token AS token,s.Telefono AS phone,s.Modo,s.Revision,s.Pendiente FROM crm.WhatsAppInbox i JOIN crm.WhatsAppSesiones s ON s.ID=i.SesionID WHERE i.Estado='Pendiente' AND i.Intentos<3 ORDER BY i.ID;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppSiguienteMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppIntentarMensaje
 @P1 BIGINT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppInbox SET Intentos=Intentos+1 WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppIntentarMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppHistorial
 @P1 INT=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 10 Texto,Tipo FROM (SELECT Texto,'user' AS Tipo,Creado FROM crm.WhatsAppInbox WHERE SesionID=@P1 AND Estado='Procesado' UNION ALL SELECT Texto,'model' AS Tipo,Creado FROM crm.WhatsAppOutbox WHERE SesionID=@P2 AND Estado='Enviado') m ORDER BY Creado DESC;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppHistorial TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppRevision
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT Revision,Modo FROM crm.WhatsAppSesiones WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppRevision TO usr_bd_whatsapp,db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCompletarMensaje
 @P1 BIGINT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppInbox SET Estado='Procesado' WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCompletarMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppConsentimiento
 @P1 BIT=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Avisos=@P1 WHERE ID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppConsentimiento TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppLeerAccion
 @P1 VARCHAR(200)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT Resultado FROM crm.WhatsAppAcciones WHERE Clave=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppLeerAccion TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppValidarSesion
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT Modo,Revision FROM crm.WhatsAppSesiones WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppValidarSesion TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppActivo

AS
BEGIN
 SET NOCOUNT ON;
 SELECT Activo FROM crm.WhatsAppControl WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppActivo TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppGuardarAccion
 @P1 VARCHAR(200)=NULL,
 @P2 INT=NULL,
 @P3 VARCHAR(80)=NULL,
 @P4 NVARCHAR(MAX)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 INSERT crm.WhatsAppAcciones(Clave,SesionID,Herramienta,Resultado) VALUES(@P1,@P2,@P3,@P4);
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppGuardarAccion TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCancelarObsoletos

AS
BEGIN
 SET NOCOUNT ON;
 UPDATE o SET Estado='Cancelado' FROM crm.WhatsAppOutbox o JOIN crm.WhatsAppSesiones s ON s.ID=o.SesionID WHERE o.Estado='Pendiente' AND ((o.Tipo='IA' AND (s.Modo<>'IA' OR s.Revision<>o.Revision)) OR (o.Tipo='Aviso' AND s.Avisos=0));
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCancelarObsoletos TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppSiguienteEnvio

AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 1 o.*,s.JID FROM crm.WhatsAppOutbox o JOIN crm.WhatsAppSesiones s ON s.ID=o.SesionID JOIN crm.WhatsAppControl c ON c.ID=1 WHERE c.Activo=1 AND o.Estado='Pendiente' AND o.Intentos<5 AND o.Disponible<=SYSUTCDATETIME() ORDER BY o.ID;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppSiguienteEnvio TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppResultadoEnvio
 @P1 BIT=NULL,
 @P2 BIGINT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppOutbox SET Intentos=Intentos+1,Estado=CASE WHEN @P1=1 THEN 'Enviado' WHEN Intentos>=4 THEN 'Fallido' ELSE 'Pendiente' END,Disponible=DATEADD(second,POWER(2,Intentos)*15,SYSUTCDATETIME()) WHERE ID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppResultadoEnvio TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBloquearEnvio
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT Modo,Revision,Avisos FROM crm.WhatsAppSesiones WITH(UPDLOCK,HOLDLOCK) WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBloquearEnvio TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBloquearControl

AS
BEGIN
 SET NOCOUNT ON;
 SELECT Activo FROM crm.WhatsAppControl WITH(HOLDLOCK) WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBloquearControl TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppHeartbeat
 @P1 NVARCHAR(40)=NULL,
 @P2 NVARCHAR(MAX)=NULL,
 @P3 NVARCHAR(MAX)=NULL,
 @P4 NVARCHAR(MAX)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppControl SET Estado=@P1,QRExpira=CASE WHEN @P2 IS NULL THEN NULL WHEN QR=@P3 THEN QRExpira ELSE DATEADD(second,75,SYSUTCDATETIME()) END,QR=@P4,Heartbeat=SYSUTCDATETIME() WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppHeartbeat TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCrearSesion
 @P1 VARCHAR(100)=NULL,
 @P2 VARCHAR(20)=NULL,
 @P3 VARCHAR(100)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 INSERT crm.WhatsAppSesiones(JID,Telefono,Token) OUTPUT INSERTED.ID VALUES(@P1,@P2,@P3);
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCrearSesion TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppHandoff
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Modo='HUMANO',Revision=Revision+1,Pendiente=NULL WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppHandoff TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBorrador
 @P1 NVARCHAR(MAX)=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Pendiente=@P1 WHERE ID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBorrador TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppLimpiarBorrador
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Pendiente=NULL WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppLimpiarBorrador TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCancelarEnvio
 @P1 BIGINT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppOutbox SET Estado='Cancelado' WHERE ID=@P1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCancelarEnvio TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppListarSesiones

AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 100 ID,Telefono,Modo,Avisos,Revision,UltimaInteraccion FROM crm.WhatsAppSesiones ORDER BY UltimaInteraccion DESC;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppListarSesiones TO db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppHistorialAdmin
 @P1 INT=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 SELECT TOP 100 Texto,Tipo,Estado,Creado FROM (SELECT Texto,'Cliente' AS Tipo,Estado,Creado FROM crm.WhatsAppInbox WHERE SesionID=@P1 UNION ALL SELECT Texto,Tipo,Estado,Creado FROM crm.WhatsAppOutbox WHERE SesionID=@P2) m ORDER BY Creado DESC;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppHistorialAdmin TO db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppActivar
 @P1 BIT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppControl SET Activo=@P1 WHERE ID=1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppActivar TO db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppModo
 @P1 VARCHAR(6)=NULL,
 @P2 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Modo=@P1,Revision=Revision+1,Pendiente=NULL WHERE ID=@P2;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppModo TO db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppCerrarMensajes
 @P1 INT=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppInbox SET Estado='Procesado' WHERE SesionID=@P1 AND Estado='Pendiente';
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppCerrarMensajes TO db_rol_gerencia,db_rol_superadmin;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppBloquearWorker

AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @r INT; EXEC @r=sys.sp_getapplock @Resource='brajhers:whatsapp:worker',@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @r;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppBloquearWorker TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppPing

AS
BEGIN
 SET NOCOUNT ON;
 SELECT 1;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppPing TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppPrepararMensaje
 @Sesion INT, @Imagen VARCHAR(255), @Texto NVARCHAR(4000)
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE crm.WhatsAppSesiones SET Imagen=COALESCE(@Imagen,Imagen),
  Pendiente=CASE WHEN UPPER(LTRIM(RTRIM(@Texto)))='CONFIRMAR' THEN Pendiente ELSE NULL END
 WHERE ID=@Sesion;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppPrepararMensaje TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppPrecio
 @P1 INT, @P2 INT
AS
BEGIN
 SET NOCOUNT ON;
 SELECT c.PrecioCotizado FROM crm.Cotizaciones c JOIN crm.WhatsAppSesiones s ON s.Token=c.SessionID
 WHERE s.ID=@P1 AND c.ID=@P2 AND c.ClienteID IS NULL AND c.Estado='Cotizada';
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppPrecio TO usr_bd_whatsapp;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('crm.WhatsAppInbox') AND name='IX_WhatsAppInbox_Pendiente')
 CREATE INDEX IX_WhatsAppInbox_Pendiente ON crm.WhatsAppInbox(Estado,ID) INCLUDE(SesionID,Intentos);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('crm.WhatsAppOutbox') AND name='IX_WhatsAppOutbox_Pendiente')
 CREATE INDEX IX_WhatsAppOutbox_Pendiente ON crm.WhatsAppOutbox(Estado,Disponible,ID) INCLUDE(SesionID,Intentos);
DECLARE @sp SYSNAME, @sql NVARCHAR(MAX); DECLARE cur_wa_deny CURSOR LOCAL FAST_FORWARD FOR SELECT p.name FROM sys.procedures p JOIN sys.schemas s ON s.schema_id = p.schema_id WHERE s.name = 'crm' AND p.name LIKE 'sp_WhatsApp%' AND p.name <> 'sp_WhatsAppNotificar'; OPEN cur_wa_deny; FETCH NEXT FROM cur_wa_deny INTO @sp; WHILE @@FETCH_STATUS = 0 BEGIN SET @sql = N'DENY EXECUTE ON OBJECT::[crm].[' + @sp + N'] TO [db_rol_cajero_pos], [db_rol_produccion], [db_rol_kiosco], [db_rol_portal_cliente];'; EXEC sp_executesql @sql; FETCH NEXT FROM cur_wa_deny INTO @sp; END; CLOSE cur_wa_deny; DEALLOCATE cur_wa_deny;
GO
