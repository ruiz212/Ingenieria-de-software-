# scripts/migrate_kiosco.py
# Migracion para permitir marcajes desde el kiosco sin usuario autenticado.

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.db import get_db_connection


def run():
    app = create_app()
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asistencia_Usuarios')
                    ALTER TABLE Asistencia DROP CONSTRAINT FK_Asistencia_Usuarios
            """)
            
            cursor.execute("""
                ALTER TABLE Asistencia ALTER COLUMN RegistradoPor INT NULL
            """)
            
            cursor.execute("""
                ALTER TABLE Asistencia ADD CONSTRAINT FK_Asistencia_Usuarios
                    FOREIGN KEY (RegistradoPor) REFERENCES Usuarios(ID)
            """)
            
            conn.commit()
            print("[OK] Migracion completada: RegistradoPor ahora es nullable.")
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Migracion: {e}")
        finally:
            conn.close()


if __name__ == '__main__':
    run()
