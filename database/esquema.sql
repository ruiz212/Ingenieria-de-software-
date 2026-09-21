-- ============================================================
-- PANADERÍA AMADA — ESQUEMA DE BASE DE DATOS (3FN Profesional)
-- SQL Server / LocalDB
-- 40+ Tablas | Generado: 2026-09-10
-- Incluye: POS, Producción, Contabilidad, RRHH (Ley Nicaragua), Estadística
-- ============================================================
-- INSTRUCCIONES: Copiar y pegar TODO este archivo en SQL Server
-- Management Studio (SSMS) y presionar F5 para ejecutar.
-- ============================================================

-- Crear la base de datos si no existe
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'PanaderiaDB')
    CREATE DATABASE PanaderiaDB;
GO

USE PanaderiaDB;
GO

-- ============================================================
-- 0. LIMPIEZA (orden inverso para respetar FK)
-- ============================================================
DROP TABLE IF EXISTS AuditLog;
DROP TABLE IF EXISTS IncidentesLaborales;
DROP TABLE IF EXISTS DeduccionesJudiciales;
DROP TABLE IF EXISTS LicenciasEmpleados;
DROP TABLE IF EXISTS DetalleNomina;
DROP TABLE IF EXISTS Nomina;
DROP TABLE IF EXISTS FeriadosNacionales;
DROP TABLE IF EXISTS Empleados;
DROP TABLE IF EXISTS Mermas;
DROP TABLE IF EXISTS Cotizaciones;
DROP TABLE IF EXISTS ConfiguracionSistema;
DROP TABLE IF EXISTS TipoCambio;
DROP TABLE IF EXISTS ArqueoCaja;
DROP TABLE IF EXISTS ConsumoLote;
DROP TABLE IF EXISTS ProduccionLotes;
DROP TABLE IF EXISTS RecetaProducto;
DROP TABLE IF EXISTS ComprasMateriaPrima;
DROP TABLE IF EXISTS MateriaPrima;
DROP TABLE IF EXISTS Proveedores;
DROP TABLE IF EXISTS ValesEmpleados;
DROP TABLE IF EXISTS EgresosPrivados;
DROP TABLE IF EXISTS Encargos;
DROP TABLE IF EXISTS Pagos;
DROP TABLE IF EXISTS DetalleIngredientes;
DROP TABLE IF EXISTS DetalleFacturas;
DROP TABLE IF EXISTS Facturas;
DROP TABLE IF EXISTS TurnosCaja;
DROP TABLE IF EXISTS Ingredientes;
DROP TABLE IF EXISTS Productos;
DROP TABLE IF EXISTS Clientes;
DROP TABLE IF EXISTS Usuarios;
DROP TABLE IF EXISTS UnidadesMedida;
DROP TABLE IF EXISTS NivelesConfianza;
DROP TABLE IF EXISTS Categorias;
DROP TABLE IF EXISTS Roles;
GO

-- ============================================================
-- 1. TABLAS CATÁLOGO (4 tablas)
-- ============================================================

CREATE TABLE Roles (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(50) NOT NULL UNIQUE,
    Descripcion VARCHAR(200) NULL
);
GO

CREATE TABLE Categorias (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(50) NOT NULL UNIQUE,
    Descripcion VARCHAR(200) NULL
);
GO

CREATE TABLE NivelesConfianza (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(50) NOT NULL UNIQUE,
    ComprasMinimas INT NOT NULL DEFAULT 0
);
GO

CREATE TABLE UnidadesMedida (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(50) NOT NULL UNIQUE,
    Abreviatura VARCHAR(10) NOT NULL
);
GO

-- ============================================================
-- 2. MÓDULO DE SEGURIDAD Y CRM (2 tablas)
-- ============================================================

CREATE TABLE Usuarios (
    ID INT PRIMARY KEY IDENTITY(1,1),
    NombreCompleto VARCHAR(100) NOT NULL,
    Username VARCHAR(50) NOT NULL UNIQUE,
    PasswordHash VARCHAR(255) NOT NULL,
    RolID INT NOT NULL,
    Activo BIT NOT NULL DEFAULT 1,
    TOTPSecret VARCHAR(32) NULL,
    TOTPEnabled BIT NOT NULL DEFAULT 0,
    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Usuarios_Roles FOREIGN KEY (RolID) REFERENCES Roles(ID)
);
GO

CREATE TABLE Clientes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    Apellidos VARCHAR(100) NULL,
    Telefono VARCHAR(20) NULL,
    PasswordHash VARCHAR(255) NULL,
    Genero VARCHAR(20) NULL,
    FechaNacimiento DATE NULL,
    RutaFotoPerfil VARCHAR(255) NULL,
    EsInvitado BIT NOT NULL DEFAULT 1,
    NivelConfianzaID INT NOT NULL,
    TotalCompras INT NOT NULL DEFAULT 0,
    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Clientes_NivelesConfianza FOREIGN KEY (NivelConfianzaID) REFERENCES NivelesConfianza(ID)
);
GO

-- ============================================================
-- 3. MÓDULO DE VENTAS Y PAGOS (8 tablas)
-- ============================================================

CREATE TABLE Productos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    CategoriaID INT NOT NULL,
    PrecioBase DECIMAL(10, 2) NOT NULL,
    EsFicticio BIT NOT NULL DEFAULT 0,
    PorcentajeDescuento DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    ImagenUrl VARCHAR(255) NULL,
    Activo BIT NOT NULL DEFAULT 1,
    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Productos_Categorias FOREIGN KEY (CategoriaID) REFERENCES Categorias(ID)
);
GO

CREATE TABLE Ingredientes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    PrecioAdicional DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    Activo BIT NOT NULL DEFAULT 1
);
GO

CREATE TABLE TurnosCaja (
    ID INT PRIMARY KEY IDENTITY(1,1),
    UsuarioID INT NOT NULL,
    FechaApertura DATETIME NOT NULL DEFAULT GETDATE(),
    FechaCierre DATETIME NULL,
    EfectivoCalculado DECIMAL(10, 2) NULL,
    TransferenciasCalculadas DECIMAL(10, 2) NULL,
    TotalVentaNeta DECIMAL(10, 2) NULL,
    Cerrado BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_TurnosCaja_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
);
GO

CREATE TABLE Facturas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    NumeroFactura VARCHAR(20) NOT NULL,
    CodigoSeguimiento VARCHAR(10) NOT NULL UNIQUE,
    FechaHora DATETIME NOT NULL DEFAULT GETDATE(),
    UsuarioID INT NOT NULL,
    ClienteID INT NULL,
    TurnoID INT NULL,
    Subtotal DECIMAL(10, 2) NOT NULL,
    IVA DECIMAL(10, 2) NOT NULL,
    Total DECIMAL(10, 2) NOT NULL,
    EsEncargo BIT NOT NULL DEFAULT 0,
    IncluyeRUC BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_Facturas_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID),
    CONSTRAINT FK_Facturas_Clientes FOREIGN KEY (ClienteID) REFERENCES Clientes(ID),
    CONSTRAINT FK_Facturas_TurnosCaja FOREIGN KEY (TurnoID) REFERENCES TurnosCaja(ID)
);
GO

CREATE TABLE DetalleFacturas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    ProductoID INT NOT NULL,
    Cantidad INT NOT NULL,
    PrecioUnitario DECIMAL(10, 2) NOT NULL,
    Subtotal DECIMAL(10, 2) NOT NULL,
    CONSTRAINT FK_DetalleFacturas_Facturas FOREIGN KEY (FacturaID) REFERENCES Facturas(ID),
    CONSTRAINT FK_DetalleFacturas_Productos FOREIGN KEY (ProductoID) REFERENCES Productos(ID)
);
GO

CREATE TABLE DetalleIngredientes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    DetalleFacturaID INT NOT NULL,
    IngredienteID INT NOT NULL,
    PrecioAplicado DECIMAL(10, 2) NOT NULL,
    CONSTRAINT FK_DetalleIngredientes_DetalleFacturas FOREIGN KEY (DetalleFacturaID) REFERENCES DetalleFacturas(ID),
    CONSTRAINT FK_DetalleIngredientes_Ingredientes FOREIGN KEY (IngredienteID) REFERENCES Ingredientes(ID)
);
GO

CREATE TABLE Pagos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    MetodoPago VARCHAR(20) NOT NULL,
    Monto DECIMAL(10, 2) NOT NULL,
    FechaPago DATETIME NOT NULL DEFAULT GETDATE(),
    NombreTransferente VARCHAR(100) NULL,
    CONSTRAINT FK_Pagos_Facturas FOREIGN KEY (FacturaID) REFERENCES Facturas(ID),
    CONSTRAINT CK_Pagos_MetodoPago CHECK (MetodoPago IN ('Efectivo', 'Transferencia', 'Efectivo USD'))
);
GO

CREATE TABLE FacturasRUC (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL UNIQUE,
    RazonSocial VARCHAR(255) NOT NULL,
    NumeroRUC VARCHAR(50) NOT NULL,
    CONSTRAINT FK_FacturasRUC_Facturas FOREIGN KEY (FacturaID) REFERENCES Facturas(ID)
);
GO

CREATE TABLE Encargos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    FechaEntrega DATETIME NOT NULL,
    Estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    PoliticasAceptadas BIT NOT NULL DEFAULT 1,
    NotasCliente VARCHAR(500) NULL,
    Especificaciones VARCHAR(MAX) NULL,
    RutaImagenReferencia VARCHAR(255) NULL,
    TelefonoContacto VARCHAR(20) NULL,
    CONSTRAINT FK_Encargos_Facturas FOREIGN KEY (FacturaID) REFERENCES Facturas(ID),
    CONSTRAINT CK_Encargos_Estado CHECK (Estado IN ('Pendiente', 'En Proceso', 'Listo', 'Entregado'))
);
GO

-- ============================================================
-- 4. MÓDULO DE CONTABILIDAD PRIVADA - Solo Admin (2 tablas)
-- ============================================================

CREATE TABLE EgresosPrivados (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Concepto VARCHAR(200) NOT NULL,
    Monto DECIMAL(10, 2) NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
    UsuarioID INT NOT NULL,
    CONSTRAINT FK_EgresosPrivados_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
);
GO

CREATE TABLE ValesEmpleados (
    ID INT PRIMARY KEY IDENTITY(1,1),
    EmpleadoID INT NOT NULL,
    Monto DECIMAL(10, 2) NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
    Descontado BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_ValesEmpleados_Usuarios FOREIGN KEY (EmpleadoID) REFERENCES Usuarios(ID)
);
GO

-- ============================================================
-- 5. MÓDULO DE INVENTARIO Y PRODUCCIÓN (5 tablas)
-- ============================================================

CREATE TABLE Proveedores (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    Telefono VARCHAR(20) NULL,
    Activo BIT NOT NULL DEFAULT 1
);
GO

CREATE TABLE MateriaPrima (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    UnidadMedidaID INT NOT NULL,
    StockActual DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    StockMinimo DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    CONSTRAINT FK_MateriaPrima_UnidadesMedida FOREIGN KEY (UnidadMedidaID) REFERENCES UnidadesMedida(ID)
);
GO

CREATE TABLE ComprasMateriaPrima (
    ID INT PRIMARY KEY IDENTITY(1,1),
    MateriaPrimaID INT NOT NULL,
    ProveedorID INT NOT NULL,
    Cantidad DECIMAL(10, 2) NOT NULL,
    CostoTotal DECIMAL(10, 2) NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_ComprasMP_MateriaPrima FOREIGN KEY (MateriaPrimaID) REFERENCES MateriaPrima(ID),
    CONSTRAINT FK_ComprasMP_Proveedores FOREIGN KEY (ProveedorID) REFERENCES Proveedores(ID)
);
GO

CREATE TABLE RecetaProducto (
    ID INT PRIMARY KEY IDENTITY(1,1),
    ProductoID INT NOT NULL,
    MateriaPrimaID INT NOT NULL,
    CantidadNecesaria DECIMAL(10, 2) NOT NULL,
    CONSTRAINT FK_RecetaProducto_Productos FOREIGN KEY (ProductoID) REFERENCES Productos(ID),
    CONSTRAINT FK_RecetaProducto_MateriaPrima FOREIGN KEY (MateriaPrimaID) REFERENCES MateriaPrima(ID)
);
GO

CREATE TABLE ProduccionLotes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    ProductoID INT NOT NULL,
    CantidadProducida INT NOT NULL,
    CantidadEsperada INT NULL,
    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_ProduccionLotes_Productos FOREIGN KEY (ProductoID) REFERENCES Productos(ID)
);
GO

CREATE TABLE ConsumoLote (
    ID INT PRIMARY KEY IDENTITY(1,1),
    LoteID INT NOT NULL,
    MateriaPrimaID INT NOT NULL,
    CantidadUsada DECIMAL(10, 2) NOT NULL,
    CONSTRAINT FK_ConsumoLote_ProduccionLotes FOREIGN KEY (LoteID) REFERENCES ProduccionLotes(ID),
    CONSTRAINT FK_ConsumoLote_MateriaPrima FOREIGN KEY (MateriaPrimaID) REFERENCES MateriaPrima(ID)
);
GO

-- ============================================================
-- 6. MÓDULO DE MERMAS Y PAN FRÍO
-- ============================================================

CREATE TABLE Mermas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    ProductoID INT NOT NULL,
    Cantidad INT NOT NULL,
    Motivo VARCHAR(50) NOT NULL,
    Observaciones VARCHAR(200) NULL,
    UsuarioID INT NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Mermas_Productos FOREIGN KEY (ProductoID) REFERENCES Productos(ID),
    CONSTRAINT FK_Mermas_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID),
    CONSTRAINT CK_Mermas_Motivo CHECK (Motivo IN ('Pan Frio', 'Defectuoso', 'Merma Horneado', 'Vencido', 'Otro'))
);
GO

-- ============================================================
-- 7. TIPO DE CAMBIO Y MULTIMONEDA
-- ============================================================

CREATE TABLE TipoCambio (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Fecha DATE NOT NULL UNIQUE,
    TasaCompra DECIMAL(10, 4) NOT NULL,
    TasaVenta DECIMAL(10, 4) NOT NULL,
    Fuente VARCHAR(50) NOT NULL DEFAULT 'Manual'
);
GO

-- ============================================================
-- 8. ARQUEO DE CAJA (Cierre de Turno)
-- ============================================================

CREATE TABLE ArqueoCaja (
    ID INT PRIMARY KEY IDENTITY(1,1),
    TurnoID INT NOT NULL,
    UsuarioID INT NOT NULL,
    -- Conteo Ciego del Cajero
    EfectivoContado DECIMAL(10, 2) NOT NULL DEFAULT 0,
    TransferenciasContadas DECIMAL(10, 2) NOT NULL DEFAULT 0,
    DolaresContados DECIMAL(10, 2) NOT NULL DEFAULT 0,
    TipoCambioUsado DECIMAL(10, 4) NULL,
    -- Valores Calculados por el Sistema
    EfectivoSistema DECIMAL(10, 2) NOT NULL DEFAULT 0,
    TransferenciasSistema DECIMAL(10, 2) NOT NULL DEFAULT 0,
    -- Diferencia
    DiferenciaEfectivo DECIMAL(10, 2) NOT NULL DEFAULT 0,
    DiferenciaTransferencias DECIMAL(10, 2) NOT NULL DEFAULT 0,
    -- Observaciones
    Observaciones VARCHAR(500) NULL,
    FechaArqueo DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_ArqueoCaja_TurnosCaja FOREIGN KEY (TurnoID) REFERENCES TurnosCaja(ID),
    CONSTRAINT FK_ArqueoCaja_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
);
GO

-- ============================================================
-- 9. CONFIGURACIÓN DEL SISTEMA
-- ============================================================

CREATE TABLE ConfiguracionSistema (
    Clave VARCHAR(50) PRIMARY KEY NOT NULL,
    Valor VARCHAR(255) NOT NULL,
    Descripcion VARCHAR(200) NULL
);
GO

-- ============================================================
-- 10. COTIZACIONES DE PASTELES (Portal Web)
-- ============================================================

CREATE TABLE Cotizaciones (
    ID INT PRIMARY KEY IDENTITY(1,1),
    ClienteID INT NULL,
    SessionID VARCHAR(36) NULL,
    Especificaciones VARCHAR(MAX) NOT NULL,
    FechaEntrega DATE NOT NULL,
    RutaImagenReferencia VARCHAR(255) NULL,
    TelefonoContacto VARCHAR(20) NULL,
    Estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    PrecioCotizado DECIMAL(10, 2) NULL,
    FechaSolicitud DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Cotizaciones_Clientes FOREIGN KEY (ClienteID) REFERENCES Clientes(ID),
    CONSTRAINT CK_Cotizaciones_Estado CHECK (Estado IN ('Pendiente', 'Cotizada', 'Aceptada', 'Rechazada'))
);
GO

-- ============================================================
-- 11. MÓDULO DE RECURSOS HUMANOS (Ley Nicaragua)
-- ============================================================

-- Empleados: Expediente completo según Ley 787 y Ley 185
CREATE TABLE Empleados (
    ID INT PRIMARY KEY IDENTITY(1,1),
    UsuarioID INT NULL,
    -- Datos Personales
    NombreCompleto VARCHAR(150) NOT NULL,
    Cedula VARCHAR(20) NOT NULL UNIQUE,
    FechaNacimiento DATE NULL,
    Genero VARCHAR(10) NULL,
    Direccion VARCHAR(300) NULL,
    Telefono VARCHAR(20) NULL,
    CorreoElectronico VARCHAR(100) NULL,
    NumeroINSS VARCHAR(20) NULL,
    -- Datos Laborales
    Cargo VARCHAR(100) NOT NULL,
    FechaIngreso DATE NOT NULL,
    FechaEgreso DATE NULL,
    TipoContrato VARCHAR(30) NOT NULL DEFAULT 'Indefinido',
    TipoJornada VARCHAR(20) NOT NULL DEFAULT 'Diurna',
    SalarioBase DECIMAL(10, 2) NOT NULL,
    FormaPago VARCHAR(20) NOT NULL DEFAULT 'Mensual',
    -- Estado
    EstadoEmpleado VARCHAR(20) NOT NULL DEFAULT 'Activo',
    MotivoEgreso VARCHAR(100) NULL,
    -- Consentimiento Ley 787
    ConsentimientoDatos BIT NOT NULL DEFAULT 0,
    FechaConsentimiento DATETIME NULL,
    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Empleados_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID),
    CONSTRAINT CK_Empleados_Contrato CHECK (TipoContrato IN ('Indefinido', 'Determinado', 'Por Obra')),
    CONSTRAINT CK_Empleados_Jornada CHECK (TipoJornada IN ('Diurna', 'Nocturna', 'Mixta')),
    CONSTRAINT CK_Empleados_FormaPago CHECK (FormaPago IN ('Semanal', 'Catorcenal', 'Quincenal', 'Mensual')),
    CONSTRAINT CK_Empleados_Estado CHECK (EstadoEmpleado IN ('Activo', 'Subsidio', 'Licencia', 'Suspendido', 'Liquidado'))
);
GO

-- Feriados Nacionales de Nicaragua (Art. 66 Ley 185)
CREATE TABLE FeriadosNacionales (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Fecha DATE NOT NULL,
    Descripcion VARCHAR(100) NOT NULL,
    Anio INT NOT NULL,
    EsMovil BIT NOT NULL DEFAULT 0
);
GO

-- Nómina: Encabezado de corrida de nómina
CREATE TABLE Nomina (
    ID INT PRIMARY KEY IDENTITY(1,1),
    EmpleadoID INT NOT NULL,
    PeriodoInicio DATE NOT NULL,
    PeriodoFin DATE NOT NULL,
    -- Ingresos
    SalarioBruto DECIMAL(10, 2) NOT NULL,
    HorasExtras DECIMAL(10, 2) NOT NULL DEFAULT 0,
    MontoHorasExtras DECIMAL(10, 2) NOT NULL DEFAULT 0,
    OtrosIngresos DECIMAL(10, 2) NOT NULL DEFAULT 0,
    TotalDevengado DECIMAL(10, 2) NOT NULL,
    -- Deducciones de Ley
    INSSLaboral DECIMAL(10, 2) NOT NULL DEFAULT 0,
    IRMensual DECIMAL(10, 2) NOT NULL DEFAULT 0,
    -- Deducciones Voluntarias/Judiciales
    PensionAlimenticia DECIMAL(10, 2) NOT NULL DEFAULT 0,
    ValesDescontados DECIMAL(10, 2) NOT NULL DEFAULT 0,
    OtrasDeducciones DECIMAL(10, 2) NOT NULL DEFAULT 0,
    TotalDeducciones DECIMAL(10, 2) NOT NULL,
    -- Resultado
    SalarioNeto DECIMAL(10, 2) NOT NULL,
    -- Aportes Patronales (Información)
    INSSPatronal DECIMAL(10, 2) NOT NULL DEFAULT 0,
    INATEC DECIMAL(10, 2) NOT NULL DEFAULT 0,
    -- Metadatos
    Estado VARCHAR(20) NOT NULL DEFAULT 'Borrador',
    FechaGeneracion DATETIME NOT NULL DEFAULT GETDATE(),
    GeneradoPor INT NULL,
    CONSTRAINT FK_Nomina_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
    CONSTRAINT FK_Nomina_GeneradoPor FOREIGN KEY (GeneradoPor) REFERENCES Usuarios(ID),
    CONSTRAINT CK_Nomina_Estado CHECK (Estado IN ('Borrador', 'Aprobada', 'Pagada', 'Anulada'))
);
GO

-- Detalle de Nómina: Desglose de cálculos para auditoría
CREATE TABLE DetalleNomina (
    ID INT PRIMARY KEY IDENTITY(1,1),
    NominaID INT NOT NULL,
    Concepto VARCHAR(100) NOT NULL,
    Tipo VARCHAR(10) NOT NULL,
    Monto DECIMAL(10, 2) NOT NULL,
    Descripcion VARCHAR(200) NULL,
    CONSTRAINT FK_DetalleNomina_Nomina FOREIGN KEY (NominaID) REFERENCES Nomina(ID),
    CONSTRAINT CK_DetalleNomina_Tipo CHECK (Tipo IN ('Ingreso', 'Deduccion', 'Patronal'))
);
GO

-- Licencias y Permisos de Empleados
CREATE TABLE LicenciasEmpleados (
    ID INT PRIMARY KEY IDENTITY(1,1),
    EmpleadoID INT NOT NULL,
    TipoLicencia VARCHAR(50) NOT NULL,
    FechaInicio DATE NOT NULL,
    FechaFin DATE NOT NULL,
    DiasOtorgados INT NOT NULL,
    PagoEmpleador DECIMAL(5, 2) NOT NULL DEFAULT 100.00,
    PagoINSS DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    Observaciones VARCHAR(300) NULL,
    AprobadoPor INT NULL,
    FechaRegistro DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_LicenciasEmpleados_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
    CONSTRAINT FK_LicenciasEmpleados_Aprobador FOREIGN KEY (AprobadoPor) REFERENCES Usuarios(ID),
    CONSTRAINT CK_Licencias_Tipo CHECK (TipoLicencia IN (
        'Vacaciones', 'Enfermedad Comun', 'Maternidad', 'Paternidad',
        'Matrimonio', 'Luto', 'Riesgo Profesional', 'Permiso Personal', 'Otro'
    ))
);
GO

-- Deducciones Judiciales (Pensiones Alimenticias - Ley 870)
CREATE TABLE DeduccionesJudiciales (
    ID INT PRIMARY KEY IDENTITY(1,1),
    EmpleadoID INT NOT NULL,
    TipoDeduccion VARCHAR(30) NOT NULL,
    Beneficiario VARCHAR(150) NOT NULL,
    PorcentajeSalarioNeto DECIMAL(5, 2) NOT NULL,
    MontoFijo DECIMAL(10, 2) NULL,
    NumeroJuzgado VARCHAR(50) NULL,
    FechaInicio DATE NOT NULL,
    FechaFin DATE NULL,
    Activa BIT NOT NULL DEFAULT 1,
    CONSTRAINT FK_DeduccionesJudiciales_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
    CONSTRAINT CK_DeduccionesJudiciales_Tipo CHECK (TipoDeduccion IN ('Pension Alimenticia', 'Embargo Comercial'))
);
GO

-- Incidentes Laborales (Ley 618)
CREATE TABLE IncidentesLaborales (
    ID INT PRIMARY KEY IDENTITY(1,1),
    EmpleadoID INT NOT NULL,
    TipoIncidente VARCHAR(30) NOT NULL,
    Gravedad VARCHAR(20) NOT NULL,
    Descripcion VARCHAR(MAX) NOT NULL,
    FechaIncidente DATETIME NOT NULL,
    FechaReporte DATETIME NOT NULL DEFAULT GETDATE(),
    NotificadoMITRAB BIT NOT NULL DEFAULT 0,
    FechaNotificacionMITRAB DATETIME NULL,
    AccionesCorrectivas VARCHAR(MAX) NULL,
    RegistradoPor INT NOT NULL,
    CONSTRAINT FK_IncidentesLaborales_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
    CONSTRAINT FK_IncidentesLaborales_Registrador FOREIGN KEY (RegistradoPor) REFERENCES Usuarios(ID),
    CONSTRAINT CK_Incidentes_Tipo CHECK (TipoIncidente IN ('Accidente', 'Casi Accidente', 'Enfermedad Ocupacional')),
    CONSTRAINT CK_Incidentes_Gravedad CHECK (Gravedad IN ('Leve', 'Grave', 'Muy Grave', 'Mortal'))
);
GO

-- ============================================================
-- 12. LOG DE AUDITORÍA
-- ============================================================

CREATE TABLE AuditLog (
    ID INT PRIMARY KEY IDENTITY(1,1),
    UsuarioID INT NULL,
    Accion VARCHAR(100) NOT NULL,
    Entidad VARCHAR(50) NOT NULL,
    EntidadID INT NULL,
    DatosAntes VARCHAR(MAX) NULL,
    DatosDespues VARCHAR(MAX) NULL,
    IP VARCHAR(45) NULL,
    FechaHora DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_AuditLog_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
);
GO

-- ============================================================
-- 13. ÍNDICES DE RENDIMIENTO
-- ============================================================

CREATE INDEX IX_Productos_CategoriaID ON Productos(CategoriaID);
CREATE INDEX IX_Facturas_UsuarioID ON Facturas(UsuarioID);
CREATE INDEX IX_Facturas_ClienteID ON Facturas(ClienteID);
CREATE INDEX IX_Facturas_TurnoID ON Facturas(TurnoID);
CREATE INDEX IX_Facturas_FechaHora ON Facturas(FechaHora);
CREATE INDEX IX_DetalleFacturas_FacturaID ON DetalleFacturas(FacturaID);
CREATE INDEX IX_Pagos_FacturaID ON Pagos(FacturaID);
CREATE INDEX IX_Encargos_Estado ON Encargos(Estado);
CREATE INDEX IX_TurnosCaja_UsuarioID ON TurnosCaja(UsuarioID);
CREATE INDEX IX_Nomina_EmpleadoID ON Nomina(EmpleadoID);
CREATE INDEX IX_Nomina_Periodo ON Nomina(PeriodoInicio, PeriodoFin);
CREATE INDEX IX_Mermas_Fecha ON Mermas(Fecha);
CREATE INDEX IX_AuditLog_FechaHora ON AuditLog(FechaHora);
CREATE UNIQUE NONCLUSTERED INDEX UQ_Clientes_Telefono ON Clientes(Telefono) WHERE Telefono IS NOT NULL;
GO

-- ============================================================
-- 14. DATOS INICIALES (Catálogos y Datos de Prueba)
-- ============================================================

-- Roles del sistema
INSERT INTO Roles (Nombre, Descripcion) VALUES
('SuperAdmin', 'Control total del sistema, datos y accesos'),
('Admin', 'Gerente: gestiona ajustes, usuarios y contabilidad'),
('Estandar', 'Dependienta: acceso al POS y cierre de turno'),
('Invitado', 'Panadero/Taller: acceso al monitor de cocina y catálogo');
GO

-- Categorías de productos
INSERT INTO Categorias (Nombre, Descripcion) VALUES
('Pan Salado', 'Bolillos, pan pizza, baguettes'),
('Pan Dulce', 'Conchas, donas, panuelitos'),
('Reposteria', 'Pasteles y queques para encargo'),
('Bebidas', 'Cafe, gaseosas, jugos'),
('Postres Frios', 'Tres leches, selva negra, gelatinas'),
('Galletas', 'Galletas de jamon, mantequilla');
GO

-- Niveles de confianza de clientes
INSERT INTO NivelesConfianza (Nombre, ComprasMinimas) VALUES
('Nuevo', 0),
('Frecuente', 3),
('VIP', 10);
GO

-- Unidades de medida
INSERT INTO UnidadesMedida (Nombre, Abreviatura) VALUES
('Kilogramo', 'Kg'),
('Litro', 'Lt'),
('Unidad', 'Ud'),
('Libra', 'Lb'),
('Gramo', 'g');
GO

-- Usuarios de prueba
INSERT INTO Usuarios (NombreCompleto, Username, PasswordHash, RolID) VALUES
('Amada Calero Leiva', 'amada', 'hashed_pwd_aqui', 2),
('Dependienta Turno 1', 'ventas1', 'hashed_pwd_aqui', 3),
('Dependienta Turno 2', 'ventas2', 'hashed_pwd_aqui', 3);
GO

-- Productos de prueba
INSERT INTO Productos (Nombre, CategoriaID, PrecioBase, EsFicticio) VALUES
('Bolillo',                          1, 5.00,   0),
('Pan Pizza',                        1, 15.00,  0),
('Galleta de Jamon',                 6, 8.00,   0),
('Panuelito',                        2, 10.00,  0),
('Concha de Vainilla',               2, 12.00,  0),
('Dona de Chocolate',                2, 10.00,  0),
('Milanesa',                         2, 25.00,  0),
('Cafe Americano',                   4, 20.00,  0),
('Gaseosa',                          4, 15.00,  0),
('Pastel Tres Leches (1 Lb)',        3, 350.00, 0),
('Pastel de Chocolate (1 Lb)',       3, 400.00, 0),
('Pastel Ficticio Chocolate (1 Lb)', 3, 280.00, 1),
('Selva Negra',                      5, 380.00, 0);
GO

-- Ingredientes extra para personalización de pasteles
INSERT INTO Ingredientes (Nombre, PrecioAdicional) VALUES
('Relleno de Fresa',           50.00),
('Relleno de Cajeta',          40.00),
('Cobertura de Chocolate',     30.00),
('Extra Nuez',                 60.00),
('Cake Topper Personalizado',  80.00),
('Aplicaciones en Relieve',   120.00);
GO

-- Cliente genérico de mostrador
INSERT INTO Clientes (Nombre, Telefono, NivelConfianzaID, TotalCompras, EsInvitado) VALUES
('Cliente General (Mostrador)', NULL, 1, 0, 1);
GO

-- Configuración del Sistema
INSERT INTO ConfiguracionSistema (Clave, Valor, Descripcion) VALUES
('nombre_negocio', 'Panadería Amada Calero Leiva', 'Nombre del negocio'),
('ruc_negocio', '', 'Número RUC del negocio'),
('direccion_negocio', '', 'Dirección fiscal del negocio'),
('telefono_negocio', '', 'Teléfono de contacto'),
('iva_porcentaje', '15', 'Porcentaje de IVA aplicado (0 si exento)'),
('moneda_simbolo', 'C$', 'Símbolo de moneda'),
('tipo_cambio_usd', '36.6243', 'Tipo de cambio oficial USD→C$ (manual)'),
('totp_obligatorio', '0', 'Verificación en dos pasos obligatoria'),
('permitir_invitados', '1', 'Permitir acceso como cliente invitado'),
('max_items_factura', '50', 'Máximo de líneas por factura'),
('whatsapp_negocio', '50588888888', 'Número de WhatsApp empresarial'),
('inss_laboral', '7.00', 'Tasa INSS Laboral (%)'),
('inss_patronal_menos50', '21.50', 'Tasa INSS Patronal (<50 empleados) (%)'),
('inss_patronal_mas50', '22.50', 'Tasa INSS Patronal (>=50 empleados) (%)'),
('inatec', '2.00', 'Tasa INATEC (%)');
GO

-- Feriados Nacionales de Nicaragua 2026 (Art. 66 Ley 185)
INSERT INTO FeriadosNacionales (Fecha, Descripcion, Anio, EsMovil) VALUES
('2026-01-01', 'Año Nuevo', 2026, 0),
('2026-04-02', 'Jueves Santo', 2026, 1),
('2026-04-03', 'Viernes Santo', 2026, 1),
('2026-05-01', 'Día del Trabajo', 2026, 0),
('2026-05-30', 'Día de la Madre', 2026, 0),
('2026-07-19', 'Día de la Revolución', 2026, 0),
('2026-08-01', 'Fiesta de Santo Domingo (Managua)', 2026, 0),
('2026-08-10', 'Fiesta de Santo Domingo (Managua)', 2026, 0),
('2026-09-14', 'Batalla de San Jacinto', 2026, 0),
('2026-09-15', 'Día de la Independencia', 2026, 0),
('2026-12-08', 'Día de la Inmaculada Concepción', 2026, 0),
('2026-12-25', 'Navidad', 2026, 0);
GO

-- Tabla progresiva IR (Art. 23, Ley 822) - Rangos anuales en C$
-- Estos valores se leen desde ConfiguracionSistema como tablas maestras
INSERT INTO ConfiguracionSistema (Clave, Valor, Descripcion) VALUES
('ir_tabla', '[{"desde":0,"hasta":100000,"base":0,"tasa":0,"exceso":0},{"desde":100000.01,"hasta":200000,"base":0,"tasa":15,"exceso":100000},{"desde":200000.01,"hasta":350000,"base":15000,"tasa":20,"exceso":200000},{"desde":350000.01,"hasta":500000,"base":45000,"tasa":25,"exceso":350000},{"desde":500000.01,"hasta":999999999,"base":82500,"tasa":30,"exceso":500000}]', 'Tabla progresiva IR Art.23 Ley 822 (JSON)');
GO

PRINT '============================================================';
PRINT 'PANADERIA AMADA - Esquema creado exitosamente.';
PRINT '40+ tablas | 14 indices | RRHH Ley Nicaragua | Datos iniciales';
PRINT '============================================================';
GO
