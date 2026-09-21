import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

def run_migration():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Hacer TurnoID nullable en Facturas
        print("Alterando tabla Facturas...")
        cursor.execute("ALTER TABLE Facturas ALTER COLUMN TurnoID INT NULL")
        
        # Eliminar registros de turnos basura (si los clientes ya crearon alguno)
        print("Eliminando turnos basura de clientes...")
        cursor.execute("""
            DELETE FROM TurnosCaja 
            WHERE UsuarioID IN (
                SELECT u.ID FROM Usuarios u 
                JOIN Roles r ON u.RolID = r.ID 
                WHERE r.Nombre IN ('Cliente', 'Invitado')
            )
        """)
        
        conn.commit()
        print("Migración completada exitosamente.")
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
