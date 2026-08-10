# app/db.py
# Conexión centralizada a SQL Server

import pyodbc
from flask import current_app


def get_db_connection():
    """Obtiene una conexión a SQL Server usando la configuración de la app."""
    return pyodbc.connect(current_app.config['SQL_SERVER_CONNECTION_STRING'])


def obtener_o_crear_turno(user_id):
    """Obtiene el turno activo del usuario o crea uno nuevo."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ID FROM TurnosCaja WHERE UsuarioID = ? AND Cerrado = 0", user_id
    )
    row = cursor.fetchone()
    if row:
        turno_id = row.ID
    else:
        cursor.execute(
            "INSERT INTO TurnosCaja (UsuarioID) OUTPUT INSERTED.ID VALUES (?)", user_id
        )
        turno_id = cursor.fetchone()[0]
        conn.commit()
    conn.close()
    return turno_id
