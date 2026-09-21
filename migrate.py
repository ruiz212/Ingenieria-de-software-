import pyodbc

def run_migration():
    print("Conectando a la base de datos...")
    drivers = [driver for driver in pyodbc.drivers() if 'SQL Server' in driver or 'ODBC Driver' in driver]
    if not drivers:
        print("No SQL Server ODBC drivers found.")
        return
    driver = drivers[-1]
    server = r'DESKTOP-A45EBFM'
    conn_db_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
    
    try:
        conn = pyodbc.connect(conn_db_str, autocommit=True)
        cursor = conn.cursor()

        sql = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Cotizaciones' AND xtype='U')
        BEGIN
            CREATE TABLE Cotizaciones (
                ID INT PRIMARY KEY IDENTITY(1,1),
                ClienteID INT NULL,
                SessionID VARCHAR(255) NULL,
                Especificaciones VARCHAR(MAX) NOT NULL,
                FechaEntrega DATETIME NOT NULL,
                RutaImagenReferencia VARCHAR(255) NULL,
                TelefonoContacto VARCHAR(20) NULL,
                Estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
                PrecioCotizado DECIMAL(10,2) NULL,
                FechaSolicitud DATETIME NOT NULL DEFAULT GETDATE(),
                CONSTRAINT FK_Cotizaciones_Clientes FOREIGN KEY (ClienteID) REFERENCES Clientes(ID),
                CONSTRAINT CK_Cotizaciones_Estado CHECK (Estado IN ('Pendiente', 'Cotizada', 'Aceptada', 'Rechazada'))
            );
            PRINT 'Tabla Cotizaciones creada exitosamente.'
        END
        ELSE
        BEGIN
            PRINT 'La tabla Cotizaciones ya existe.'
        END
        """
        
        cursor.execute(sql)
        print("Migración completada con éxito.")
    except Exception as e:
        print(f"Error al ejecutar la migración: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    run_migration()
