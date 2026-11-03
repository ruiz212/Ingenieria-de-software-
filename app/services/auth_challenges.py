"""Short-lived authentication state shared by all workers in SQL Server.

Cookies carry only random identifiers. SMS codes are keyed hashes; verified
SMS grants are consumed in the transaction that inserts the customer.
"""
import hashlib
import hmac
import re
import secrets
import time

import pyotp
from flask import current_app

from app.db import get_db_connection, execute_sp

TTL = 600
MAX_ATTEMPTS = 5
TOTP_WINDOW_SECONDS = 900
SMS_RESEND_SECONDS = 60
FIELDS = ('Token', 'Kind', 'Subject', 'Verifier', 'Secret', 'Binding',
          'ExpiresAt', 'Attempts', 'Verified', 'Consumed')


class ResendTooSoon(ValueError):
    pass


class TOTPLocked(ValueError):
    pass


def normalize_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+\d\s().-]+', value.strip()):
        raise ValueError('El teléfono debe tener formato internacional válido.')
    phone = re.sub(r'[\s().-]', '', value)
    if re.fullmatch(r'\d{8}', phone):
        phone = '+505' + phone
    elif re.fullmatch(r'505\d{8}', phone):
        phone = '+' + phone
    elif re.fullmatch(r'00505\d{8}', phone):
        phone = '+' + phone[2:]
    if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        raise ValueError('El teléfono debe tener formato internacional válido.')
    return phone


def _digest(value):
    key = current_app.config['SECRET_KEY']
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def user_binding(secret, enabled):
    return _digest(f'{secret or ""}:{int(bool(enabled))}')


def _read(cursor, token, lock=False):
    if not token or not isinstance(token, str):
        return None
    hint = ' WITH (UPDLOCK, HOLDLOCK)' if lock else ''
    row = execute_sp(
        cursor,
        'seguridad.sp_LeerDesafioAuth',
        (token, 1 if lock else 0),
        fallback_sql=f'SELECT {", ".join(FIELDS)} FROM AuthChallenges{hint} WHERE Token = ?',
        fallback_params=(token,),
    ).fetchone()
    return dict(zip(FIELDS, row)) if row else None


def _valid(row, kind=None):
    return bool(row and not row['Consumed'] and row['ExpiresAt'] > int(time.time())
                and (row['Attempts'] < MAX_ATTEMPTS or
                     (row['Kind'] == 'sms' and row['Verified'] and row['Attempts'] == MAX_ATTEMPTS))
                and (kind is None or row['Kind'] == kind))


def _totp_failures_in_window(cursor, subject: str, now_ts: int | None = None) -> int:
    now_val = int(time.time()) if now_ts is None else int(now_ts)
    min_expires = now_val + TTL - TOTP_WINDOW_SECONDS
    row = execute_sp(
        cursor,
        'seguridad.sp_ObtenerFallosTOTPRecientes',
        (str(subject), min_expires),
        fallback_sql=(
            "SELECT COALESCE(SUM(Attempts), 0) FROM AuthChallenges WITH (UPDLOCK, HOLDLOCK) "
            "WHERE Subject = ? AND Kind LIKE 'totp%' AND Verified = 0 AND ExpiresAt > ?"
        ),
        fallback_params=(str(subject), min_expires),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def get_totp_failures(subject, user_type: str = 'emp') -> int:
    conn = get_db_connection()
    try:
        return _totp_failures_in_window(conn.cursor(), str(subject))
    finally:
        conn.close()


def is_totp_locked(subject, user_type: str = 'emp') -> bool:
    return get_totp_failures(subject, user_type=user_type) >= MAX_ATTEMPTS


def clear_totp_failures(subject, user_type: str = 'emp') -> None:
    conn = get_db_connection()
    try:
        execute_sp(
            conn.cursor(),
            'seguridad.sp_LimpiarFallosTOTPUsuario',
            (str(subject),),
            fallback_sql="UPDATE AuthChallenges SET Verified = 1, Consumed = 1, Attempts = 0 WHERE Subject = ? AND Kind LIKE 'totp%'",
            fallback_params=(str(subject),),
        )
        conn.commit()
    finally:
        conn.close()


def create(kind, subject, verifier='', secret='', binding=''):
    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if kind == 'sms':
            # The indexed subject range stays locked until INSERT/commit: a
            # fresh browser or another worker cannot bypass the send interval.
            previous = execute_sp(
                cursor,
                'seguridad.sp_ObtenerMaxExpiracionDesafioSMS',
                (subject, 'sms'),
                fallback_sql='SELECT MAX(ExpiresAt) FROM AuthChallenges WITH (UPDLOCK, HOLDLOCK) WHERE Subject = ? AND Kind = ?',
            ).fetchone()
            if previous and previous[0] is not None and int(previous[0]) - TTL + SMS_RESEND_SECONDS > int(time.time()):
                raise ResendTooSoon('Espera 60 segundos antes de solicitar otro código para este teléfono.')
        else:
            if _totp_failures_in_window(cursor, str(subject)) >= MAX_ATTEMPTS:
                raise TOTPLocked('Cuenta bloqueada temporalmente por exceso de intentos TOTP fallidos. Intente más tarde.')
        # A new challenge replaces every outstanding grant for this identity.
        family = 'sms' if kind == 'sms' else 'totp%'
        execute_sp(
            cursor,
            'seguridad.sp_ConsumirDesafiosFamilia',
            (subject, family),
            fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Subject = ? AND Kind LIKE ?',
        )
        execute_sp(
            cursor,
            'seguridad.sp_InsertarDesafioAuth',
            (token, kind, subject, verifier, secret, binding, int(time.time()) + TTL),
            fallback_sql='INSERT INTO AuthChallenges (' + ', '.join(FIELDS) + ') VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0)',
        )
        conn.commit()
        return token
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revoke(token):
    if not token:
        return
    conn = get_db_connection()
    try:
        execute_sp(
            conn.cursor(),
            'seguridad.sp_RevocarDesafioPorToken',
            (token,),
            fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Token = ?',
        )
        conn.commit()
    finally:
        conn.close()


def issue_sms(phone):
    code = f'{secrets.randbelow(1000000):06d}'
    token = create('sms', phone, verifier=_digest(phone + ':' + code))
    return token, code


def verify_sms(token, phone, code):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = _read(cursor, token, lock=True)
        if not _valid(row, 'sms') or row['Verified']:
            return False
        execute_sp(
            cursor,
            'seguridad.sp_IncrementarIntentosDesafio',
            (token,),
            fallback_sql='UPDATE AuthChallenges SET Attempts = Attempts + 1 WHERE Token = ?',
        )
        ok = (phone == row['Subject'] and isinstance(code, str)
              and bool(re.fullmatch(r'\d{6}', code))
              and hmac.compare_digest(row['Verifier'], _digest(phone + ':' + code)))
        if ok:
            execute_sp(
                cursor,
                'seguridad.sp_MarcarDesafioVerificado',
                (token,),
                fallback_sql='UPDATE AuthChallenges SET Verified = 1 WHERE Token = ?',
            )
        conn.commit()
        return ok
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consume_sms(cursor, token, phone):
    """Caller owns the transaction; failed INSERT must roll back consumption."""
    row = _read(cursor, token, lock=True)
    if not _valid(row, 'sms') or not row['Verified'] or row['Subject'] != phone:
        return False
    execute_sp(
        cursor,
        'seguridad.sp_RevocarDesafioPorToken',
        (token,),
        fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Token = ?',
    )
    return True


def start_totp(user, enroll=False):
    return create('totp_enroll' if enroll else 'totp_login', str(user.id),
                  secret=pyotp.random_base32() if enroll else '',
                  binding=user_binding(user.totp_secret, user.totp_enabled))


def pending_totp(token, kind):
    if not token:
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = _read(cursor, token)
        if not _valid(row, kind):
            return None
        if _totp_failures_in_window(cursor, str(row['Subject'])) >= MAX_ATTEMPTS:
            return None
        return row
    finally:
        conn.close()


def complete_totp(token, code, kind):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = _read(cursor, token, lock=True)
        if not _valid(row, kind):
            return None
        if _totp_failures_in_window(cursor, str(row['Subject'])) >= MAX_ATTEMPTS:
            execute_sp(
                cursor,
                'seguridad.sp_RevocarDesafioPorToken',
                (token,),
                fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Token = ?',
            )
            conn.commit()
            return None
        user = execute_sp(
            cursor,
            'seguridad.sp_ObtenerTOTPActivoUsuario',
            (int(row['Subject']),),
            fallback_sql='SELECT TOTPSecret, TOTPEnabled FROM Usuarios WITH (UPDLOCK, HOLDLOCK) WHERE ID = ? AND Activo = 1',
        ).fetchone()
        if not user or not hmac.compare_digest(row['Binding'], user_binding(user[0], user[1])):
            execute_sp(
                cursor,
                'seguridad.sp_RevocarDesafioPorToken',
                (token,),
                fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Token = ?',
            )
            conn.commit()
            return None
        secret = row['Secret'] if kind == 'totp_enroll' else user[0]
        ok = bool(secret and isinstance(code, str) and re.fullmatch(r'\d{6}', code)
                  and pyotp.TOTP(secret).verify(code))
        if ok:
            if kind == 'totp_enroll':
                execute_sp(
                    cursor,
                    'seguridad.sp_ActivarTOTPUsuario',
                    (secret, int(row['Subject'])),
                    fallback_sql='UPDATE Usuarios SET TOTPSecret = ?, TOTPEnabled = 1 WHERE ID = ?',
                )
            execute_sp(
                cursor,
                'seguridad.sp_LimpiarFallosTOTPUsuario',
                (row['Subject'],),
                fallback_sql="UPDATE AuthChallenges SET Verified = 1, Consumed = 1, Attempts = 0 WHERE Subject = ? AND Kind LIKE 'totp%'",
                fallback_params=(row['Subject'],),
            )
        else:
            execute_sp(
                cursor,
                'seguridad.sp_IncrementarIntentosDesafio',
                (token,),
                fallback_sql='UPDATE AuthChallenges SET Attempts = Attempts + 1 WHERE Token = ?',
            )
            if _totp_failures_in_window(cursor, str(row['Subject'])) >= MAX_ATTEMPTS:
                execute_sp(
                    cursor,
                    'seguridad.sp_RevocarDesafioPorToken',
                    (token,),
                    fallback_sql='UPDATE AuthChallenges SET Consumed = 1 WHERE Token = ?',
                )
        conn.commit()
        return int(row['Subject']) if ok else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
