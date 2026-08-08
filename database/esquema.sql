-- ============================================================
-- PANADERÍA AMADA — ESQUEMA DE BASE DE DATOS (3FN Profesional)
-- SQL Server / LocalDB
-- 21 Tablas | Generado: 2026-08-08
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
    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_Usuarios_Roles FOREIGN KEY (RolID) REFERENCES Roles(ID)
);
GO

CREATE TABLE Clientes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    Telefono VARCHAR(20) NULL,
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
    TurnoID INT NOT NULL,
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
    CONSTRAINT CK_Pagos_MetodoPago CHECK (MetodoPago IN ('Efectivo', 'Transferencia'))
);
GO

CREATE TABLE Encargos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    FechaEntrega DATETIME NOT NULL,
    Estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    PoliticasAceptadas BIT NOT NULL DEFAULT 1,
    NotasCliente VARCHAR(500) NULL,
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
-- 6. ÍNDICES DE RENDIMIENTO
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
GO

-- ============================================================
-- 7. DATOS INICIALES (Catálogos y Datos de Prueba)
-- ============================================================

-- Roles del sistema
INSERT INTO Roles (Nombre, Descripcion) VALUES
('SuperAdmin', 'Control total del sistema, datos y accesos'),
('Admin', 'Gerente: gestiona ajustes, usuarios y contabilidad'),
('Estandar', 'Dependienta: acceso al POS y cierre de turno'),
('Invitado', 'Solo lectura: panaderos y acceso al catalogo');
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

-- Productos de prueba (IDs de Categorias: 1=Pan Salado, 2=Pan Dulce, 3=Reposteria, 4=Bebidas, 5=Postres Frios, 6=Galletas)
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

-- Ingredientes extra para personalizacion de pasteles
INSERT INTO Ingredientes (Nombre, PrecioAdicional) VALUES
('Relleno de Fresa',           50.00),
('Relleno de Cajeta',          40.00),
('Cobertura de Chocolate',     30.00),
('Extra Nuez',                 60.00),
('Cake Topper Personalizado',  80.00),
('Aplicaciones en Relieve',   120.00);
GO

-- Cliente generico de mostrador
INSERT INTO Clientes (Nombre, Telefono, NivelConfianzaID, TotalCompras) VALUES
('Cliente General (Mostrador)', NULL, 1, 0);
GO

PRINT '============================================================';
PRINT 'PANADERIA AMADA - Esquema creado exitosamente.';
PRINT '21 tablas | 9 indices | Datos iniciales cargados.';
PRINT '============================================================';
GO
