from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE Empleados ADD HoraEntrada TIME NULL")
        cursor.execute("ALTER TABLE Empleados ADD HoraSalida TIME NULL")
        print("Columnas HoraEntrada y HoraSalida añadidas a Empleados.")
    except Exception as e:
        print(f"Aviso Empleados: {e}")

    conn.commit()
    conn.close()
    print("Migración de horarios personalizados completada.")
