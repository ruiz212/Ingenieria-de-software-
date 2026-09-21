import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print("Agregando columnas a la tabla Encargos...")
        # Check and add Especificaciones
        try:
            cursor.execute("ALTER TABLE Encargos ADD Especificaciones VARCHAR(MAX) NULL")
            print("Columna Especificaciones agregada.")
        except Exception as e:
            print("Especificaciones ya existe o error:", e)
            
        # Check and add RutaImagenReferencia
        try:
            cursor.execute("ALTER TABLE Encargos ADD RutaImagenReferencia VARCHAR(255) NULL")
            print("Columna RutaImagenReferencia agregada.")
        except Exception as e:
            print("RutaImagenReferencia ya existe o error:", e)
            
        # Check and add TelefonoContacto
        try:
            cursor.execute("ALTER TABLE Encargos ADD TelefonoContacto VARCHAR(20) NULL")
            print("Columna TelefonoContacto agregada.")
        except Exception as e:
            print("TelefonoContacto ya existe o error:", e)

        conn.commit()
        print("Migración de Encargos completada.")
            
    except Exception as e:
        conn.rollback()
        print(f"Error general: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        run_migration()
