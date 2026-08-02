-- Creación de tablas principales para la Panadería (Sistema Profesional)

CREATE TABLE Productos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    Categoria VARCHAR(50) NOT NULL, -- 'Mostrador', 'Encargo'
    Precio DECIMAL(10, 2) NOT NULL,
    ImagenUrl VARCHAR(255) NULL
);

CREATE TABLE Facturas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    NumeroFactura VARCHAR(20) NOT NULL,
    CodigoSeguimiento VARCHAR(10) UNIQUE NOT NULL,
    Fecha DATETIME DEFAULT GETDATE(),
    Subtotal DECIMAL(10, 2) NOT NULL,
    IVA DECIMAL(10, 2) NOT NULL,
    Total DECIMAL(10, 2) NOT NULL,
    TipoVenta VARCHAR(50) DEFAULT 'Contado' -- 'Contado', 'Encargo'
);

CREATE TABLE Ingredientes (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    PrecioAdicional DECIMAL(10, 2) DEFAULT 0.00
);

CREATE TABLE DetalleFacturas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    ProductoID INT NOT NULL,
    NombreProducto VARCHAR(200) NOT NULL,
    OpcionesExtra VARCHAR(255) NULL,
    Cantidad INT NOT NULL,
    PrecioUnitario DECIMAL(10, 2) NOT NULL,
    Subtotal DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (FacturaID) REFERENCES Facturas(ID),
    FOREIGN KEY (ProductoID) REFERENCES Productos(ID)
);

CREATE TABLE Encargos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    FacturaID INT NOT NULL,
    NombreCliente VARCHAR(100) NULL,
    Telefono VARCHAR(20) NULL,
    FechaEntrega DATETIME NOT NULL,
    Adelanto DECIMAL(10, 2) NOT NULL,
    SaldoPendiente DECIMAL(10, 2) NOT NULL,
    Estado VARCHAR(50) DEFAULT 'Pendiente', -- 'Pendiente', 'En Proceso', 'Listo', 'Entregado'
    FOREIGN KEY (FacturaID) REFERENCES Facturas(ID)
);

-- Insertar datos de prueba
INSERT INTO Productos (Nombre, Categoria, Precio, ImagenUrl) VALUES
('Bolillo', 'Mostrador', 5.00, 'bolillo.jpg'),
('Pan Pizza', 'Mostrador', 15.00, 'pizza.jpg'),
('Milanesa', 'Mostrador', 25.00, 'milanesa.jpg'),
('Pastel de Tres Leches', 'Encargo', 350.00, 'tres_leches.jpg'),
('Pastel de Chocolate', 'Encargo', 400.00, 'chocolate.jpg');

INSERT INTO Ingredientes (Nombre, PrecioAdicional) VALUES
('Relleno de Fresa', 50.00),
('Relleno de Cajeta', 40.00),
('Cobertura de Chocolate', 30.00),
('Extra Nuez', 60.00);
