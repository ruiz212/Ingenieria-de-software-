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
  Revision INT NOT NULL DEFAULT 0, Avisos BIT NOT NULL DEFAULT 1,
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
 DECLARE @Token VARCHAR(100), @Telefono VARCHAR(20), @Imagen VARCHAR(255), @Tel8 VARCHAR(20);
 SELECT @Token=Token,@Telefono=Telefono,@Imagen=Imagen,
  @Tel8=RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(ISNULL(Telefono,''),'+',''),'-',''),' ',''),'.',''),8)
  FROM crm.WhatsAppSesiones WHERE ID=@Sesion;
 IF @Token IS NULL THROW 52026,'Sesión WhatsApp inexistente.',1;
 IF @Operacion='listar'
 BEGIN
  SELECT TOP 20 c.ID,c.Especificaciones,c.FechaEntrega,c.Estado,c.PrecioCotizado
   FROM crm.Cotizaciones c LEFT JOIN crm.Clientes cl ON cl.ID=c.ClienteID
   WHERE (c.ClienteID IS NULL AND c.SessionID=@Token)
    OR (LEN(@Tel8)=8 AND RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(c.TelefonoContacto)),''),cl.Telefono,''),'+',''),'-',''),' ',''),'.',''),8)=@Tel8)
   ORDER BY c.ID DESC;
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
 UPDATE c WITH(UPDLOCK,HOLDLOCK)
  SET Estado=CASE WHEN @Operacion='aceptar' THEN 'Aceptada' ELSE 'Rechazada' END
  FROM crm.Cotizaciones c LEFT JOIN crm.Clientes cl ON cl.ID=c.ClienteID
  WHERE c.ID=@Cotizacion AND c.Estado='Cotizada' AND c.PrecioCotizado=@PrecioEsperado
   AND ((c.ClienteID IS NULL AND c.SessionID=@Token)
    OR (LEN(@Tel8)=8 AND RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(c.TelefonoContacto)),''),cl.Telefono,''),'+',''),'-',''),' ',''),'.',''),8)=@Tel8));
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
 DECLARE @Texto NVARCHAR(4000), @Clave VARCHAR(200), @Sesion INT, @Tel8 VARCHAR(20);
 IF @Tipo='cotizacion'
 BEGIN
  SELECT @Tel8=RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(c.TelefonoContacto)),''),cl.Telefono,''),'+',''),'-',''),' ',''),'.',''),8)
  FROM crm.Cotizaciones c LEFT JOIN crm.Clientes cl ON cl.ID=c.ClienteID WHERE c.ID=@ID;
  IF LEN(@Tel8)=8 AND @Tel8 NOT LIKE '%[^0-9]%'
   AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppSesiones WHERE RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(Telefono,'+',''),'-',''),' ',''),'.',''),8)=@Tel8)
   AND NOT EXISTS(SELECT 1 FROM crm.Cotizaciones c JOIN crm.WhatsAppSesiones s ON s.Token=c.SessionID WHERE c.ID=@ID)
  BEGIN
   INSERT crm.WhatsAppSesiones(JID,Telefono,Token,Avisos)
    VALUES(CONCAT('505',@Tel8,'@s.whatsapp.net'),CONCAT('+505',@Tel8),LOWER(REPLACE(CONVERT(VARCHAR(36),NEWID()),'-','')),1);
  END;
  SELECT TOP 1 @Sesion=s.ID,
   @Texto=CASE
    WHEN c.Estado='Cotizada' THEN CONCAT(N'🍰 Brajher''s Cake: Tu cotización COT-',RIGHT(CONCAT('0000',c.ID),4),N' está lista por C$ ',CONVERT(NVARCHAR(30),c.PrecioCotizado),N' (Entrega: ',CONVERT(NVARCHAR(10),c.FechaEntrega,103),N'). Indica el código COT-',RIGHT(CONCAT('0000',c.ID),4),N' y si deseas aceptarla o rechazarla.')
    WHEN c.Estado='Rechazada' THEN CONCAT(N'🍰 Brajher''s Cake: Tu cotización COT-',RIGHT(CONCAT('0000',c.ID),4),N' fue marcada como Rechazada. Escribe HUMANO si deseas ajustar tu pedido.')
    WHEN c.Estado='Aceptada' THEN CONCAT(N'🍰 Brajher''s Cake: Confirmamos tu aceptación de la cotización COT-',RIGHT(CONCAT('0000',c.ID),4),N' por C$ ',CONVERT(NVARCHAR(30),c.PrecioCotizado),N'. Recuerda realizar el adelanto mínimo del 50% en caja.')
    ELSE NULL END,
   @Clave=CONCAT('quote:',c.ID,':',c.Estado,':',ISNULL(CONVERT(VARCHAR(30),c.PrecioCotizado),'0'))
  FROM crm.Cotizaciones c LEFT JOIN crm.Clientes cl ON cl.ID=c.ClienteID
  JOIN crm.WhatsAppSesiones s ON (c.SessionID=s.Token OR (LEN(@Tel8)=8 AND RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(s.Telefono,'+',''),'-',''),' ',''),'.',''),8)=@Tel8))
  WHERE c.ID=@ID AND c.Estado IN ('Cotizada','Rechazada','Aceptada') AND s.Avisos=1;
 END
 ELSE IF @Tipo='pedido'
 BEGIN
  SELECT @Tel8=RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(e.TelefonoContacto)),''),cl.Telefono,''),'+',''),'-',''),' ',''),'.',''),8)
  FROM ventas.Encargos e JOIN ventas.Facturas f ON f.ID=e.FacturaID LEFT JOIN crm.Clientes cl ON cl.ID=f.ClienteID WHERE f.ID=@ID;
  IF LEN(@Tel8)=8 AND @Tel8 NOT LIKE '%[^0-9]%'
   AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppSesiones WHERE RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(Telefono,'+',''),'-',''),' ',''),'.',''),8)=@Tel8)
  BEGIN
   INSERT crm.WhatsAppSesiones(JID,Telefono,Token,Avisos)
    VALUES(CONCAT('505',@Tel8,'@s.whatsapp.net'),CONCAT('+505',@Tel8),LOWER(REPLACE(CONVERT(VARCHAR(36),NEWID()),'-','')),1);
  END;
  SELECT TOP 1 @Sesion=s.ID,
   @Texto=CASE
    WHEN e.Estado='Pendiente' THEN CONCAT(N'🧾 Brajher''s Cake: Tu pedido ',f.NumeroFactura,N' fue registrado (Estado: Pendiente, entrega ',CONVERT(NVARCHAR(10),e.FechaEntrega,103),N'). Código de seguimiento: ',f.CodigoSeguimiento,N'.')
    WHEN e.Estado='En Proceso' THEN CONCAT(N'👩‍🍳 Brajher''s Cake: Tu pedido ',f.NumeroFactura,N' está En Proceso en pastelería (Entrega: ',CONVERT(NVARCHAR(10),e.FechaEntrega,103),N'). Código de seguimiento: ',f.CodigoSeguimiento,N'.')
    WHEN e.Estado='Listo' THEN CONCAT(N'🎂 Brajher''s Cake: ¡Tu pedido ',f.NumeroFactura,N' está Listo para retirar! Consulta el saldo con tu código privado de seguimiento ',f.CodigoSeguimiento,N'.')
    WHEN e.Estado='Entregado' THEN CONCAT(N'✅ Brajher''s Cake: Tu pedido ',f.NumeroFactura,N' fue marcado como Entregado. ¡Gracias por preferirnos!')
    ELSE NULL END,
   @Clave=CONCAT('order:',f.ID,':',e.Estado)
  FROM ventas.Encargos e JOIN ventas.Facturas f ON f.ID=e.FacturaID LEFT JOIN crm.Clientes cl ON cl.ID=f.ClienteID
  JOIN crm.WhatsAppSesiones s ON LEN(@Tel8)=8 AND RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(s.Telefono,'+',''),'-',''),' ',''),'.',''),8)=@Tel8
  WHERE f.ID=@ID AND (f.EstadoFiscal IS NULL OR f.EstadoFiscal='Emitida') AND e.Estado IN ('Pendiente','En Proceso','Listo','Entregado') AND s.Avisos=1;
 END;
 IF @Sesion IS NOT NULL AND @Texto IS NOT NULL AND NOT EXISTS(SELECT 1 FROM crm.WhatsAppOutbox WITH(UPDLOCK,HOLDLOCK) WHERE Clave=@Clave)
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
 INSERT crm.WhatsAppOutbox(SesionID,Clave,Texto,Tipo,Revision) SELECT @P2,@P3,@P4,@P5,@P6 WHERE NOT EXISTS(SELECT 1 FROM crm.WhatsAppOutbox WITH(UPDLOCK,HOLDLOCK) WHERE Clave=@P1);
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
 SELECT TOP 20 Texto,Tipo FROM (SELECT Texto,'user' AS Tipo,Creado FROM crm.WhatsAppInbox WHERE SesionID=@P1 AND Estado='Procesado' UNION ALL SELECT Texto,'model' AS Tipo,Creado FROM crm.WhatsAppOutbox WHERE SesionID=@P2 AND Estado IN ('Enviado','Pendiente')) m ORDER BY Creado DESC;
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
 SELECT TOP 100 Texto,Tipo,Estado,Creado,Imagen FROM (SELECT Texto,'Cliente' AS Tipo,Estado,Creado,Imagen FROM crm.WhatsAppInbox WHERE SesionID=@P1 UNION ALL SELECT Texto,Tipo,Estado,Creado,CAST(NULL AS VARCHAR(255)) AS Imagen FROM crm.WhatsAppOutbox WHERE SesionID=@P2) m ORDER BY Creado DESC;
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
  Pendiente=CASE WHEN UPPER(LTRIM(RTRIM(@Texto))) IN ('CANCELAR','ANULAR') THEN NULL ELSE Pendiente END
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
 SELECT c.PrecioCotizado FROM crm.Cotizaciones c JOIN crm.WhatsAppSesiones s ON (s.Token=c.SessionID OR c.TelefonoContacto=s.Telefono)
 WHERE s.ID=@P1 AND c.ID=@P2 AND c.Estado='Cotizada';
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppPrecio TO usr_bd_whatsapp;
GO
CREATE OR ALTER PROCEDURE crm.sp_WhatsAppPedidosCliente
 @Sesion INT
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @Tel8 VARCHAR(20);
 SELECT @Tel8=RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(ISNULL(Telefono,''),'+',''),'-',''),' ',''),'.',''),8)
  FROM crm.WhatsAppSesiones WHERE ID=@Sesion;
 IF LEN(@Tel8)<>8 BEGIN SELECT TOP 0 CAST(NULL AS VARCHAR(50)) AS NumeroFactura; RETURN; END;
 SELECT TOP 10 f.NumeroFactura, f.CodigoSeguimiento, e.Estado, e.FechaEntrega, f.Total,
  ISNULL((SELECT SUM(p.Monto) FROM ventas.Pagos p WHERE p.FacturaID=f.ID), 0) AS Pagado
 FROM ventas.Encargos e JOIN ventas.Facturas f ON f.ID=e.FacturaID
 LEFT JOIN crm.Clientes cl ON cl.ID=f.ClienteID
 WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal='Emitida')
  AND RIGHT(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(e.TelefonoContacto)),''),cl.Telefono,''),'+',''),'-',''),' ',''),'.',''),8)=@Tel8
 ORDER BY f.ID DESC;
END;
GO
GRANT EXECUTE ON crm.sp_WhatsAppPedidosCliente TO usr_bd_whatsapp;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('crm.WhatsAppInbox') AND name='IX_WhatsAppInbox_Pendiente')
 CREATE INDEX IX_WhatsAppInbox_Pendiente ON crm.WhatsAppInbox(Estado,ID) INCLUDE(SesionID,Intentos);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('crm.WhatsAppOutbox') AND name='IX_WhatsAppOutbox_Pendiente')
 CREATE INDEX IX_WhatsAppOutbox_Pendiente ON crm.WhatsAppOutbox(Estado,Disponible,ID) INCLUDE(SesionID,Intentos);
DECLARE @sp SYSNAME, @sql NVARCHAR(MAX); DECLARE cur_wa_deny CURSOR LOCAL FAST_FORWARD FOR SELECT p.name FROM sys.procedures p JOIN sys.schemas s ON s.schema_id = p.schema_id WHERE s.name = 'crm' AND p.name LIKE 'sp_WhatsApp%' AND p.name <> 'sp_WhatsAppNotificar'; OPEN cur_wa_deny; FETCH NEXT FROM cur_wa_deny INTO @sp; WHILE @@FETCH_STATUS = 0 BEGIN SET @sql = N'DENY EXECUTE ON OBJECT::[crm].[' + @sp + N'] TO [db_rol_cajero_pos], [db_rol_produccion], [db_rol_kiosco], [db_rol_portal_cliente];'; EXEC sp_executesql @sql; FETCH NEXT FROM cur_wa_deny INTO @sp; END; CLOSE cur_wa_deny; DEALLOCATE cur_wa_deny;
GO
