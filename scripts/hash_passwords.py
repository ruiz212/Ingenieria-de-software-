import sys
import os
from werkzeug.security import generate_password_hash
import pyodbc

# Añadir el directorio padre al sys.path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def update_passwords():
    print("Conectando a la base de datos...")
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Generar hash fuerte (pbkdf2:sha256) para la contraseña por defecto "123456"
        default_password = "123456"
        hashed_password = generate_password_hash(default_password)
        
        # Actualizar a todos los usuarios
        cursor.execute("UPDATE Usuarios SET PasswordHash = ?", hashed_password)
        conn.commit()
        
        print(f"Éxito: Se actualizaron las contraseñas de {cursor.rowcount} usuarios.")
        print(f"Ahora puedes iniciar sesión con cualquier usuario usando la contraseña: {default_password}")
        
    except Exception as e:
        print("Error actualizando contraseñas:", e)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    update_passwords()
