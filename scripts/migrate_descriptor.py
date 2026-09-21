import os
import sys

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if FaceDescriptor column exists
        cursor.execute("SELECT COL_LENGTH('Empleados', 'FaceDescriptor')")
        result = cursor.fetchone()
        
        if result[0] is None:
            # Column does not exist, add it
            cursor.execute("ALTER TABLE Empleados ADD FaceDescriptor VARCHAR(MAX) NULL")
            print("Columna FaceDescriptor añadida a la tabla Empleados exitosamente.")
        else:
            print("La columna FaceDescriptor ya existe en la tabla Empleados.")
    except Exception as e:
        print(f"Error al modificar Empleados: {e}")

    conn.commit()
    conn.close()
    
    print("Migración FaceDescriptor completada.")
