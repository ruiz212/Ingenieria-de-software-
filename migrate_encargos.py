from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE Encargos ADD Especificaciones VARCHAR(MAX) NULL")
        print("Añadido Especificaciones")
    except Exception as e:
        print(e)
    try:
        cursor.execute("ALTER TABLE Encargos ADD RutaImagenReferencia VARCHAR(255) NULL")
        print("Añadido RutaImagenReferencia")
    except Exception as e:
        print(e)
    try:
        cursor.execute("ALTER TABLE Encargos ADD TelefonoContacto VARCHAR(20) NULL")
        print("Añadido TelefonoContacto")
    except Exception as e:
        print(e)
    
    conn.commit()
    conn.close()
    print("Migración completada.")
