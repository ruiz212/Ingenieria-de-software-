# app/models.py
# Modelos de datos del sistema respaldados por Stored Procedures por esquema

from flask import g, has_request_context
from flask_login import UserMixin  # type: ignore
from app.db import get_db_connection, execute_sp
from app.extensions import login_manager


class User(UserMixin):
    """Modelo de usuario que representa una fila de la tabla seguridad.Usuarios."""

    def __init__(self, id, username, nombre_completo, rol_id, rol_nombre=None, totp_secret=None, totp_enabled=False):
        self.id = id
        self.username = username
        self.nombre_completo = nombre_completo
        self.rol_id = rol_id
        self.rol_nombre = rol_nombre
        self.totp_secret = totp_secret
        self.totp_enabled = totp_enabled

    def get_id(self):
        """Devuelve un ID modificado con prefijo para diferenciar entre Empleados y Clientes."""
        return f"emp_{self.id}"

    @staticmethod
    def get_by_id(user_id):
        """Busca un usuario activo por su ID ejecutando seguridad.sp_ObtenerUsuarioPorID."""
        conn = get_db_connection(inject_context=False)
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'seguridad.sp_ObtenerUsuarioPorID',
            (user_id,),
            fallback_sql=(
                "SELECT u.ID, u.Username, u.NombreCompleto, u.RolID, r.Nombre AS RolNombre, u.TOTPSecret, u.TOTPEnabled "
                "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
                "WHERE u.ID = ? AND u.Activo = 1"
            ),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            rol_nombre = getattr(row, 'RolNombre', getattr(row, 'Nombre', None))
            return User(
                id=row.ID, username=row.Username,
                nombre_completo=row.NombreCompleto,
                rol_id=row.RolID, rol_nombre=rol_nombre,
                totp_secret=row.TOTPSecret, totp_enabled=row.TOTPEnabled
            )
        return None

    @staticmethod
    def get_by_username(username):
        """Busca un usuario activo por su username ejecutando seguridad.sp_AutenticarUsuario."""
        conn = get_db_connection(inject_context=False)
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'seguridad.sp_AutenticarUsuario',
            (username,),
            fallback_sql=(
                "SELECT u.ID, u.Username, u.PasswordHash, u.NombreCompleto, u.RolID, r.Nombre AS RolNombre, u.TOTPSecret, u.TOTPEnabled "
                "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
                "WHERE u.Username = ? AND u.Activo = 1"
            ),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            rol_nombre = getattr(row, 'RolNombre', getattr(row, 'Nombre', None))
            user = User(
                id=row.ID, username=row.Username,
                nombre_completo=row.NombreCompleto,
                rol_id=row.RolID, rol_nombre=rol_nombre,
                totp_secret=row.TOTPSecret, totp_enabled=row.TOTPEnabled
            )
            return user, row.PasswordHash
        return None, None


class Cliente(UserMixin):
    """Modelo de usuario que representa un cliente en la tabla crm.Clientes."""

    def __init__(self, id, nombre, apellidos, telefono, es_invitado, nivel_confianza_id, fecha_nacimiento=None):
        self.id = id
        self.nombre = nombre
        self.apellidos = apellidos
        self.telefono = telefono
        self.es_invitado = es_invitado
        self.nivel_confianza_id = nivel_confianza_id
        self.fecha_nacimiento = fecha_nacimiento
        self.rol_nombre = "Cliente" if not es_invitado else "Invitado"

    def get_id(self):
        return f"cli_{self.id}"

    @property
    def is_invitado(self):
        return self.es_invitado

    @staticmethod
    def get_by_id(cliente_id):
        conn = get_db_connection(inject_context=False)
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'crm.sp_ObtenerClientePorID',
            (cliente_id,),
            fallback_sql=(
                "SELECT ID, Nombre, Apellidos, Telefono, EsInvitado, NivelConfianzaID, FechaNacimiento "
                "FROM Clientes WHERE ID = ?"
            ),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return Cliente(
                id=row.ID, nombre=row.Nombre, apellidos=row.Apellidos,
                telefono=row.Telefono, es_invitado=row.EsInvitado,
                nivel_confianza_id=row.NivelConfianzaID,
                fecha_nacimiento=getattr(row, 'FechaNacimiento', None)
            )
        return None

    @staticmethod
    def get_by_telefono(telefono):
        conn = get_db_connection(inject_context=False)
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'crm.sp_ObtenerClientePorTelefono',
            (telefono,),
            fallback_sql=(
                "SELECT ID, Nombre, Apellidos, Telefono, PasswordHash, EsInvitado, NivelConfianzaID, FechaNacimiento "
                "FROM Clientes WHERE Telefono = ?"
            ),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            cliente = Cliente(
                id=row.ID, nombre=row.Nombre, apellidos=row.Apellidos,
                telefono=row.Telefono, es_invitado=row.EsInvitado,
                nivel_confianza_id=row.NivelConfianzaID,
                fecha_nacimiento=getattr(row, 'FechaNacimiento', None)
            )
            return cliente, row.PasswordHash
        return None, None


@login_manager.user_loader
def load_user(user_id):
    """Callback requerido por Flask-Login para recargar el usuario de sesión.
    Se utiliza el prefijo en el ID para identificar si es Empleado o Cliente."""
    if not user_id:
        return None

    if has_request_context():
        g._loading_auth_user = True
    try:
        try:
            prefix, real_id = user_id.split('_', 1)
            if prefix == 'emp':
                return User.get_by_id(real_id)
            elif prefix == 'cli':
                return Cliente.get_by_id(real_id)
        except ValueError:
            pass

        # Manejo temporal por si hay una sesión antigua sin prefijo
        return User.get_by_id(user_id)
    finally:
        if has_request_context():
            g._loading_auth_user = False
