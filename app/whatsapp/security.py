"""Reauthentication for account changes, with a shared SQL attempt budget."""
import pyotp
from werkzeug.security import check_password_hash
from app.models import User
from app.whatsapp.repository import connection


def reserve_attempt():
    # Reserves an attempt atomically, including concurrent web workers. Fail closed.
    with connection() as (_, cur):
        cur.execute('EXEC crm.sp_WhatsAppIntentoAdmin')
        return bool(cur.fetchone()[0])


def record_auth_result(success):
    with connection() as (_, cur):
        cur.execute('EXEC crm.sp_WhatsAppResultadoAuth ?', success)


def verify_admin(current, password, otp):
    if not reserve_attempt():
        raise ValueError('Demasiados intentos. Espere 15 minutos antes de volver a verificar su identidad.')
    user, password_hash = User.get_by_username(current.username)
    valid = bool(user and user.id == current.id and user.rol_nombre in ('Admin', 'SuperAdmin')
                 and password_hash and isinstance(password, str) and len(password) <= 256
                 and check_password_hash(password_hash, password))
    if valid and user.totp_enabled:
        valid = bool(user.totp_secret and isinstance(otp, str) and len(otp) == 6
                     and otp.isdigit() and pyotp.TOTP(user.totp_secret).verify(otp, valid_window=1))
    record_auth_result(valid)
    if not valid:
        raise ValueError('No se pudo verificar su identidad. Revise su contraseña y su código de dos pasos.')
