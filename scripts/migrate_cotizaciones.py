import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if Cotizaciones exists
        cursor.execute("SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Cotizaciones'")
        if not cursor.fetchone():
            print("Creando tabla Cotizaciones...")
            cursor.execute("""
                CREATE TABLE Cotizaciones (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    ClienteID INT NULL,
                    SessionID VARCHAR(50) NULL,
                    Especificaciones VARCHAR(MAX) NOT NULL,
                    FechaEntrega DATETIME NOT NULL,
                    RutaImagenReferencia VARCHAR(255) NULL,
                    TelefonoContacto VARCHAR(20) NULL,
                    PrecioCotizado DECIMAL(10,2) NULL,
                    Estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
                    FechaSolicitud DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_Cotizaciones_Clientes FOREIGN KEY (ClienteID) REFERENCES Clientes(ID)
                )
            """)
            conn.commit()
            print("Tabla Cotizaciones creada exitosamente.")
        else:
            print("La tabla Cotizaciones ya existe.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        run_migration()
