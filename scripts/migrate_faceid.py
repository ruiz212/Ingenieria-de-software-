import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE Empleados ADD FotoPerfil VARCHAR(255) NULL")
        print("Columna FotoPerfil añadida a Empleados.")
    except Exception as e:
        print(f"Aviso Empleados: {e}")

    conn.commit()
    conn.close()
    
    # Create uploads directory if it doesn't exist
    upload_path = os.path.join(app.root_path, 'static', 'uploads', 'faces')
    os.makedirs(upload_path, exist_ok=True)
    print(f"Directorio de fotos creado en {upload_path}")
    print("Migración FaceID completada.")
