-- Creación de tablas principales para la Panadería

CREATE TABLE Productos (
    ID INT PRIMARY KEY IDENTITY(1,1),
    Nombre VARCHAR(100) NOT NULL,
    Precio DECIMAL(10, 2) NOT NULL,
    ImagenUrl VARCHAR(255) NULL
);

CREATE TABLE Ventas (
    ID INT PRIMARY KEY IDENTITY(1,1),
    ProductoID INT NOT NULL,
    Cantidad INT NOT NULL,
    Total DECIMAL(10, 2) NOT NULL,
    Fecha DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ProductoID) REFERENCES Productos(ID)
);

-- Insertar datos de prueba
INSERT INTO Productos (Nombre, Precio, ImagenUrl) VALUES
('Bolillo', 5.00, 'bolillo.jpg'),
('Pan Pizza', 15.00, 'pizza.jpg'),
('Milanesa', 25.00, 'milanesa.jpg');
