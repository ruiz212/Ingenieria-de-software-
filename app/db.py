# app/db.py
# Conexión centralizada a SQL Server, Contexto de Sesión, Roles de BD y Ejecución de SPs

from contextlib import contextmanager
from functools import wraps
import re
import pyodbc
from flask import current_app, g, has_request_context, request, session
from flask_login import current_user
from werkzeug.exceptions import ServiceUnavailable
from app.services.request_context import client_ip

ROLE_TO_DB_ROLE = {
    'SuperAdmin': 'db_rol_superadmin',
    'Admin': 'db_rol_gerencia',
    'Estandar': 'db_rol_cajero_pos',
    'Operativo': 'db_rol_produccion',
    'Kiosco': 'db_rol_kiosco',
    'Cliente': 'db_rol_portal_cliente',
    'Invitado': 'db_rol_portal_cliente',
}

ROLE_TO_DB_USER = {
    'SuperAdmin': 'usr_bd_superadmin',
    'Admin': 'usr_bd_gerencia',
    'Estandar': 'usr_bd_cajero_pos',
    'Operativo': 'usr_bd_produccion',
    'Kiosco': 'usr_bd_kiosco',
    'Cliente': 'usr_bd_portal_cliente',
    'Invitado': 'usr_bd_portal_cliente',
    'db_rol_superadmin': 'usr_bd_superadmin',
    'db_rol_gerencia': 'usr_bd_gerencia',
    'db_rol_cajero_pos': 'usr_bd_cajero_pos',
    'db_rol_produccion': 'usr_bd_produccion',
    'db_rol_kiosco': 'usr_bd_kiosco',
    'db_rol_portal_cliente': 'usr_bd_portal_cliente',
    'usr_bd_superadmin': 'usr_bd_superadmin',
    'usr_bd_gerencia': 'usr_bd_gerencia',
    'usr_bd_cajero_pos': 'usr_bd_cajero_pos',
    'usr_bd_produccion': 'usr_bd_produccion',
    'usr_bd_kiosco': 'usr_bd_kiosco',
    'usr_bd_portal_cliente': 'usr_bd_portal_cliente',
}


class _RoleScopedConnection:
    """Proxy transparente sobre pyodbc.Connection que garantiza REVERT al cerrar la conexión."""

    def __init__(self, conn, db_user: str):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_db_user', db_user)
        object.__setattr__(self, '_reverted', False)

    def _revert_context(self) -> None:
        if not object.__getattribute__(self, '_reverted'):
            raw_conn = object.__getattribute__(self, '_conn')
            try:
                raw_conn.rollback()
            except Exception:
                pass
            try:
                raw_conn.cursor().execute("REVERT;")
                if not getattr(raw_conn, 'autocommit', False):
                    raw_conn.commit()
            except Exception:
                pass
            object.__setattr__(self, '_reverted', True)

    def close(self) -> None:
        self._revert_context()
        object.__getattribute__(self, '_conn').close()

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_conn'), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_conn'), name, value)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def is_sqlserver_cursor(cursor) -> bool:
    """Determina si el cursor pertenece a una conexión real pyodbc de SQL Server."""
    return isinstance(cursor, pyodbc.Cursor) or type(cursor).__module__.startswith('pyodbc')


def _effective_client_ip() -> str:
    return client_ip()


def inject_session_context(conn) -> None:
    """Inyecta usuario_id, username, rol, ip, ruta_http y cotizacion_session_id en SESSION_CONTEXT."""
    raw_conn = object.__getattribute__(conn, '_conn') if isinstance(conn, _RoleScopedConnection) else conn
    if not isinstance(raw_conn, pyodbc.Connection):
        return
    if not has_request_context():
        return
    if getattr(g, '_loading_auth_user', False):
        return
    try:
        uid = None
        uname = None
        rol = None
        if current_user and getattr(current_user, 'is_authenticated', False):
            raw_id = getattr(current_user, 'id', None)
            uid = int(raw_id) if raw_id is not None and str(raw_id).isdigit() else None
            uname = getattr(current_user, 'username', None) or getattr(current_user, 'nombre', None)
            rol = getattr(current_user, 'rol_nombre', None)
        ip = _effective_client_ip()
        ruta = request.path or ''
        cot_sess = None
        try:
            cot_sess = session.get('cotizacion_session_id')
        except Exception:
            cot_sess = None

        cur = raw_conn.cursor()
        cur.execute(
            "EXEC sys.sp_set_session_context @key=N'usuario_id', @value=?; "
            "EXEC sys.sp_set_session_context @key=N'username', @value=?; "
            "EXEC sys.sp_set_session_context @key=N'rol', @value=?; "
            "EXEC sys.sp_set_session_context @key=N'ip', @value=?; "
            "EXEC sys.sp_set_session_context @key=N'ruta_http', @value=?; "
            "EXEC sys.sp_set_session_context @key=N'cotizacion_session_id', @value=?;",
            uid, uname, rol, ip, ruta, cot_sess
        )
    except Exception as exc:
        raise ServiceUnavailable('No se pudo establecer el contexto seguro de la base de datos.') from exc


@contextmanager
def as_db_role(cursor, role_or_user: str, *, revert_on_exit: bool = True):
    """Context manager que ejecuta consultas bajo el usuario contenido del rol de BD indicado."""
    if role_or_user not in ROLE_TO_DB_USER:
        raise ValueError('Nombre de rol o usuario de BD no autorizado en allowlist.')
    db_user = ROLE_TO_DB_USER[role_or_user]
    if not re.fullmatch(r'[A-Za-z0-9_]+', db_user):
        raise ValueError('Nombre de rol o usuario de BD inválido.')
    cursor.execute(f"EXECUTE AS USER = '{db_user}';")
    try:
        yield cursor
    finally:
        if revert_on_exit:
            try:
                cursor.execute("REVERT;")
            except Exception:
                pass


def _resolve_active_app_role() -> str | None:
    """Resuelve el rol de aplicación activo para activar el usuario SQL correspondiente."""
    if not has_request_context() or getattr(g, '_loading_auth_user', False):
        return None
    try:
        if current_user and getattr(current_user, 'is_authenticated', False):
            rol = getattr(current_user, 'rol_nombre', None)
            if rol in ROLE_TO_DB_ROLE:
                return rol
            raise ServiceUnavailable('No se pudo determinar un rol autorizado para la conexión.')
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable('No se pudo verificar la identidad de la conexión.') from exc
    return None


def get_db_connection(inject_context: bool = True, apply_role: bool = True):
    """Obtiene una conexión a SQL Server, inyecta SESSION_CONTEXT y activa el rol SQL del usuario."""
    is_loading_user = has_request_context() and getattr(g, '_loading_auth_user', False)
    # Resolve authentication before allocating a privileged SQL connection.
    # The explicit bootstrap path is used only by the authentication loader.
    role = _resolve_active_app_role() if apply_role and inject_context and not is_loading_user else None

    connection_string = current_app.config['SQL_SERVER_CONNECTION_STRING']
    if current_app.testing:
        from app.qa_safety import connect_qa
        conn = connect_qa(pyodbc.connect, connection_string)
    else:
        conn = pyodbc.connect(connection_string)

    try:
        if inject_context and not is_loading_user:
            inject_session_context(conn)
        if isinstance(conn, pyodbc.Connection) and inject_context and not is_loading_user:
            if role:
                with as_db_role(conn.cursor(), role, revert_on_exit=False):
                    pass
            if not getattr(conn, 'autocommit', False):
                conn.commit()
            if role:
                return _RoleScopedConnection(conn, ROLE_TO_DB_USER[role])
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            current_app.logger.warning('No se pudo revertir una conexión SQL rechazada.')
        if role:
            # EXECUTE AS may have succeeded before commit/transport failed.
            # Discard its session context before returning the handle to ODBC.
            try:
                conn.cursor().execute('REVERT;')
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            current_app.logger.warning('No se pudo cerrar una conexión SQL rechazada.')
        raise ServiceUnavailable('No se pudo establecer una conexión segura con la base de datos.') from exc
    return conn


def execute_sp(cursor, sp_name: str, params: tuple | list = (), fallback_sql: str | None = None, fallback_params: tuple | list | None = None):
    """Ejecuta un Stored Procedure (<esquema>.<sp_nombre>) en SQL Server.

    Si el cursor es un doble de prueba sintético/SQLite y se provee fallback_sql,
    ejecuta fallback_sql para preservar compatibilidad con pruebas unitarias aisladas.
    """
    if not is_sqlserver_cursor(cursor) and fallback_sql is not None:
        use_params = params if fallback_params is None else fallback_params
        if use_params:
            return cursor.execute(fallback_sql, *use_params)
        return cursor.execute(fallback_sql)

    placeholders = ', '.join('?' for _ in params)
    sql = f"EXEC {sp_name}" + (f" {placeholders}" if placeholders else "")
    try:
        if params:
            return cursor.execute(sql, *params)
        return cursor.execute(sql)
    except pyodbc.Error as err:
        try:
            from app.services.smtp_alerts import notify_error
            schema_part = sp_name.split('.')[0] if '.' in sp_name else None
            safe_params = {'param_count': len(params), 'values': ['***MASKED***' for _ in params]} if params else None
            notify_error(
                str(err),
                origen='SQL_SP',
                severidad='ERROR',
                procedimiento=sp_name,
                esquema_origen=schema_part,
                parametros_json=safe_params,
            )
        except Exception:
            pass
        raise


def call_sp(sp_name: str, params: tuple | list = (), *, fetch: str = 'all', commit: bool = False):
    """Abre conexión, ejecuta un Stored Procedure y devuelve filas o diccionarios."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(cursor, sp_name, params)
        result = None
        if fetch == 'one':
            result = cursor.fetchone()
        elif fetch == 'all':
            result = cursor.fetchall()
        elif fetch == 'dicts':
            cols = [c[0] for c in cursor.description] if cursor.description else []
            result = [dict(zip(cols, r)) for r in cursor.fetchall()] if cols else []
        if commit:
            conn.commit()
        return result
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()


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
    """Obtiene el turno activo del usuario o crea uno nuevo mediante SP."""
    row = call_sp('ventas.sp_AbrirTurnoCaja', (user_id,), fetch='one', commit=True)
    return row[0]
