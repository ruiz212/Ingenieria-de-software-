# app/db.py
# Conexión centralizada a SQL Server

import pyodbc
from flask import current_app
from functools import wraps


def get_db_connection():
    """Obtiene una conexión a SQL Server usando la configuración de la app."""
    return pyodbc.connect(current_app.config['SQL_SERVER_CONNECTION_STRING'])


def transactional(f):
    """
    Decorador para inyectar una conexión y un cursor en una función.
    Maneja el commit si todo va bien, el rollback si hay una excepción,
    y cierra la conexión al finalizar.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Inyectamos conn y cursor como kwargs
            kwargs['conn'] = conn
            kwargs['cursor'] = cursor
            result = f(*args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    return wrapper


def execute_query(query, params=None, fetch=False, fetchall=False, commit=False):
    """Helper genérico para ejecutar consultas aisladas."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        result = None
        if fetch:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
            
        if commit:
            conn.commit()
            
        return result
    except Exception as e:
        if commit:
            conn.rollback()
        raise e
    finally:
        conn.close()


def obtener_o_crear_turno(user_id):
    """Obtiene el turno activo del usuario o crea uno nuevo."""
    row = execute_query(
        "SELECT ID FROM TurnosCaja WHERE UsuarioID = ? AND Cerrado = 0",
        (user_id,),
        fetch=True
    )
    if row:
        turno_id = row.ID
    else:
        row = execute_query(
            "INSERT INTO TurnosCaja (UsuarioID) OUTPUT INSERTED.ID VALUES (?)",
            (user_id,),
            fetch=True,
            commit=True
        )
        turno_id = row[0]
    return turno_id
