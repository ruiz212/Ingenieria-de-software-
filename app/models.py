# app/models.py
# Modelos de datos del sistema

from flask_login import UserMixin
from app.db import get_db_connection
from app.extensions import login_manager


class User(UserMixin):
    """Modelo de usuario que representa una fila de la tabla Usuarios."""

    def __init__(self, id, username, nombre_completo, rol_id, rol_nombre=None):
        self.id = id
        self.username = username
        self.nombre_completo = nombre_completo
        self.rol_id = rol_id
        self.rol_nombre = rol_nombre

    @staticmethod
    def get_by_id(user_id):
        """Busca un usuario activo por su ID."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.ID, u.Username, u.NombreCompleto, u.RolID, r.Nombre "
            "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
            "WHERE u.ID = ? AND u.Activo = 1", user_id
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(
                id=row.ID, username=row.Username,
                nombre_completo=row.NombreCompleto,
                rol_id=row.RolID, rol_nombre=row.Nombre
            )
        return None

    @staticmethod
    def get_by_username(username):
        """Busca un usuario activo por su username. Devuelve (User, password_hash) o (None, None)."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.ID, u.Username, u.PasswordHash, u.NombreCompleto, u.RolID, r.Nombre "
            "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
            "WHERE u.Username = ? AND u.Activo = 1", username
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            user = User(
                id=row.ID, username=row.Username,
                nombre_completo=row.NombreCompleto,
                rol_id=row.RolID, rol_nombre=row.Nombre
            )
            return user, row.PasswordHash
        return None, None


@login_manager.user_loader
def load_user(user_id):
    """Callback requerido por Flask-Login para recargar el usuario de sesión."""
    return User.get_by_id(user_id)
