import os
from app import create_app
from app.db import get_db_connection
import pyodbc

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE Cotizaciones ADD NombreContacto VARCHAR(100) NULL;")
        conn.commit()
        print("MIGRATION SUCCESS: Added NombreContacto to Cotizaciones")
    except pyodbc.Error as e:
        print("ERROR or ALREADY APPLIED:", e)
    finally:
        conn.close()
