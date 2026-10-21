# app/auth/routes.py
# Rutas de autenticación: Login y Logout

from flask import render_template, request, redirect, url_for, flash, current_app, session, jsonify
from flask_login import login_user, login_required, logout_user, current_user  # type: ignore
from werkzeug.security import check_password_hash, generate_password_hash  # type: ignore
import os
import threading
import time
import pyotp
import qrcode
import base64
from io import BytesIO
from twilio.rest import Client

from app.auth import auth_bp
from app.models import User, Cliente
from app.db import get_db_connection, execute_sp
from urllib.parse import urlsplit
from app.services import auth_challenges
from app.services.profile_images import save_profile_image

_FALLBACK_LOCK_MUTEX = threading.Lock()
_FALLBACK_LOGIN_LOCKS: dict[tuple[str, str], dict] = {}


def _check_fallback_lock(identificador: str, ip: str) -> bool:
    key = ((identificador or '').strip().lower(), (ip or '0.0.0.0').strip())
    now = time.monotonic()
    with _FALLBACK_LOCK_MUTEX:
        entry = _FALLBACK_LOGIN_LOCKS.get(key)
        if not entry:
            return False
        if entry.get('locked_until', 0) > now:
            return True
        if entry.get('locked_until', 0) and entry['locked_until'] <= now:
            _FALLBACK_LOGIN_LOCKS.pop(key, None)
        return False


def _record_fallback_attempt(identificador: str, ip: str, exitoso: bool, max_attempts: int = 5, lock_seconds: int = 900) -> dict:
    key = ((identificador or '').strip().lower(), (ip or '0.0.0.0').strip())
    now = time.monotonic()
    with _FALLBACK_LOCK_MUTEX:
        if exitoso:
            _FALLBACK_LOGIN_LOCKS.pop(key, None)
            return {'bloqueado': False, 'recien_bloqueado': False, 'intentos': 0}
        entry = _FALLBACK_LOGIN_LOCKS.get(key)
        if not entry or (entry.get('locked_until', 0) and entry['locked_until'] <= now):
            entry = {'attempts': 1, 'locked_until': 0.0}
        else:
            entry['attempts'] += 1
        recien = False
        bloqueado = False
        if entry['attempts'] >= max_attempts:
            if entry.get('locked_until', 0) <= now:
                recien = True
            entry['locked_until'] = now + lock_seconds
            bloqueado = True
        _FALLBACK_LOGIN_LOCKS[key] = entry
        return {'bloqueado': bloqueado, 'recien_bloqueado': recien, 'intentos': entry['attempts']}


def safe_next(target):
    if target and target.startswith('/') and not target.startswith('//') and not urlsplit(target).netloc and '\\' not in target:
        return target
    return url_for('hub.main_hub')


def _customer_by_normalized_phone(phone):
    """Retain lookup compatibility with pre-migration local Nicaragua numbers."""
    customer, password_hash = Cliente.get_by_telefono(phone)
    if not customer and phone.startswith('+505') and len(phone) == 12:
        return Cliente.get_by_telefono(phone[4:])
    return customer, password_hash


def totp_is_required():
    """A missing policy is optional; an unreadable policy fails closed."""
    conn = None
    try:
        conn = get_db_connection(inject_context=False, apply_role=False)
        cursor = conn.cursor()
        execute_sp(
            cursor,
            'seguridad.sp_ObtenerValorConfiguracion',
            ('totp_obligatorio',),
            fallback_sql="SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'totp_obligatorio'",
            fallback_params=(),
        )
        row = cursor.fetchone()
        return bool(row and str(row[0]).strip().lower() in {'1', 'true', 'si', 'sí', 'yes'})
    except Exception:
        current_app.logger.exception('No se pudo leer la política global de TOTP')
        return True
    finally:
        if conn is not None:
            conn.close()


def _is_account_locked(identificador: str, ip: str) -> bool:
    if _check_fallback_lock(identificador, ip):
        return True
    if not current_app.config.get('SQL_SERVER_CONNECTION_STRING'):
        return False
    conn = None
    try:
        from app.db import is_sqlserver_cursor
        conn = get_db_connection(inject_context=False, apply_role=False)
        cursor = conn.cursor()
        if not is_sqlserver_cursor(cursor):
            return False
        execute_sp(
            cursor,
            'seguridad.sp_VerificarBloqueoCuenta',
            (identificador, ip or '0.0.0.0'),
        )
        row = cursor.fetchone()
        return bool(row and getattr(row, 'EstaBloqueado', row[5]))
    except Exception:
        return _check_fallback_lock(identificador, ip)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _record_login_attempt(identificador: str, ip: str, exitoso: bool) -> dict:
    fb_state = _record_fallback_attempt(identificador, ip, exitoso)
    if not current_app.config.get('SQL_SERVER_CONNECTION_STRING'):
        return fb_state
    conn = None
    try:
        from app.db import is_sqlserver_cursor
        conn = get_db_connection(inject_context=False, apply_role=False)
        cursor = conn.cursor()
        if not is_sqlserver_cursor(cursor):
            return fb_state
        execute_sp(
            cursor,
            'seguridad.sp_RegistrarIntentoLogin',
            (identificador, ip or '0.0.0.0', 1 if exitoso else 0, 5, 15),
        )
        row = cursor.fetchone()
        conn.commit()
        bloqueado = bool(row and row[0]) or fb_state['bloqueado']
        recien_bloqueado = bool(row and row[1]) or fb_state['recien_bloqueado']
        intentos = int(row[2]) if row and row[2] is not None else fb_state['intentos']
        if recien_bloqueado:
            from app.services.smtp_alerts import notify_error
            notify_error(
                f"Cuenta bloqueada temporalmente por fuerza bruta: '{identificador}' desde IP {ip} ({intentos} intentos fallidos).",
                origen='SEGURIDAD_AUTH',
                severidad='CRITICAL',
                numero_error=50401,
                procedimiento='seguridad.sp_RegistrarIntentoLogin',
                esquema_origen='seguridad',
                username=identificador,
                ip=ip,
                ruta_http='/login',
                persist_in_db=False,
            )
        return {'bloqueado': bloqueado, 'recien_bloqueado': recien_bloqueado, 'intentos': intentos}
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return fb_state
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pantalla de inicio de sesión."""
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))

    if request.method == 'POST':
        identificador = request.form.get('identificador', '').strip()
        password = request.form.get('password', '')
        client_ip = request.remote_addr or '0.0.0.0'

        if _is_account_locked(identificador, client_ip):
            flash("Cuenta temporalmente bloqueada por múltiples intentos fallidos. Intente más tarde.", "error")
            return render_template('login.html'), 429

        # 1. Intentar como Administrador / Empleado
        user, password_hash = User.get_by_username(identificador)
        if user and check_password_hash(password_hash, password):
            _record_login_attempt(identificador, client_ip, True)
            if getattr(user, 'totp_enabled', False) or totp_is_required():
                auth_challenges.revoke(session.pop('totp_challenge_id', None))
                enroll = not user.totp_secret or not user.totp_enabled
                session['totp_challenge_id'] = auth_challenges.start_totp(user, enroll=enroll)
                session['next_page'] = request.args.get('next')
                return redirect(url_for('auth.enroll_totp' if enroll else 'auth.login_totp'))
            else:
                login_user(user, remember=True)
                next_page = request.args.get('next')
                return redirect(safe_next(next_page))

        # 2. Intentar como Cliente
        cliente, password_hash_cli = Cliente.get_by_telefono(identificador)
        if not cliente:
            try:
                normalized = auth_challenges.normalize_phone(identificador)
            except ValueError:
                normalized = None
            if normalized:
                cliente, password_hash_cli = _customer_by_normalized_phone(normalized)
        if cliente and password_hash_cli and check_password_hash(password_hash_cli, password):
            _record_login_attempt(identificador, client_ip, True)
            login_user(cliente, remember=True)
            return redirect('/pos')

        # Si ninguno coincide
        lock_state = _record_login_attempt(identificador, client_ip, False)
        if lock_state.get('bloqueado'):
            flash("Cuenta temporalmente bloqueada por múltiples intentos fallidos. Intente más tarde.", "error")
            return render_template('login.html'), 429
        flash("Usuario/Teléfono o contraseña incorrectos", "error")

    return render_template('login.html')


def _clear_totp_session():
    for key in ('totp_challenge_id', 'setup_totp_challenge_id', 'pre_totp_user_id',
                'setup_totp_secret', 'next_page'):
        session.pop(key, None)


def _totp_page(kind, cookie_key, authenticated=False):
    token = session.get(cookie_key)
    pending = auth_challenges.pending_totp(token, kind)
    if not pending:
        _clear_totp_session()
        flash('La verificación expiró. Inicia sesión de nuevo.', 'error')
        return redirect(url_for('auth.setup_totp' if authenticated else 'auth.login'))
    user = User.get_by_id(int(pending['Subject']))
    if not user or (authenticated and user.id != current_user.id):
        _clear_totp_session()
        return redirect(url_for('auth.login'))
    if auth_challenges.user_binding(user.totp_secret, user.totp_enabled) != pending['Binding']:
        auth_challenges.revoke(token)
        _clear_totp_session()
        flash('La configuración cambió. Inicia sesión de nuevo.', 'error')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        verified_id = auth_challenges.complete_totp(token, request.form.get('totp_code'), kind)
        if verified_id:
            next_page = session.get('next_page')
            _clear_totp_session()
            if not authenticated:
                login_user(User.get_by_id(verified_id), remember=True)
            flash('Autenticación verificada.', 'success')
            return redirect(safe_next(next_page))
        flash('Código incorrecto o verificación expirada.', 'error')
        if not auth_challenges.pending_totp(token, kind):
            _clear_totp_session()
            return redirect(url_for('auth.login'))
    context = {}
    if kind == 'totp_enroll':
        secret = pending['Secret']
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name='Panadería Amada')
        buffer = BytesIO()
        qrcode.make(uri).save(buffer, format='PNG')
        context = dict(enrolling=True, secret=secret,
                       qr_base64=base64.b64encode(buffer.getvalue()).decode('ascii'))
    response = current_app.make_response(render_template('totp_login.html', **context))
    response.headers['Cache-Control'] = 'no-store'
    return response


@auth_bp.route('/login/totp', methods=['GET', 'POST'])
def login_totp():
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))
    return _totp_page('totp_login', 'totp_challenge_id')


@auth_bp.route('/login/totp/enroll', methods=['GET', 'POST'])
def enroll_totp():
    # This route never logs in until the new authenticator has been proved.
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))
    return _totp_page('totp_enroll', 'totp_challenge_id')


@auth_bp.route('/perfil/setup_totp', methods=['GET', 'POST'])
@login_required
def setup_totp():
    if getattr(current_user, 'rol_nombre', '') in ['Cliente', 'Invitado']:
        return 'Acceso denegado.', 403
    user = User.get_by_id(current_user.id)
    if user.totp_enabled and user.totp_secret:
        return redirect(url_for('hub.main_hub'))
    if request.method == 'GET' and not auth_challenges.pending_totp(
            session.get('setup_totp_challenge_id'), 'totp_enroll'):
        session['setup_totp_challenge_id'] = auth_challenges.start_totp(user, enroll=True)
    return _totp_page('totp_enroll', 'setup_totp_challenge_id', authenticated=True)


@auth_bp.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario activo."""
    es_cliente = getattr(current_user, 'rol_nombre', '') in ['Cliente', 'Invitado']
    logout_user()
    if es_cliente:
        return redirect(url_for('auth.cliente_bienvenida'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/cliente/bienvenida')
def cliente_bienvenida():
    """Pantalla inicial para clientes."""
    if current_user.is_authenticated:
        if getattr(current_user, 'rol_nombre', None) in ['Cliente', 'Invitado']:
            return redirect('/pos')
        return redirect(url_for('hub.main_hub'))
    return render_template('cliente_bienvenida.html')


def _clear_sms_session():
    for key in ('sms_challenge_id', 'sms_code', 'sms_phone', 'sms_expires_at', 'telefono_verificado'):
        session.pop(key, None)


@auth_bp.route('/cliente/registro', methods=['GET', 'POST'])
def cliente_registro():
    """The verified phone grant and customer INSERT form one transaction."""
    if current_user.is_authenticated:
        return redirect('/pos')
    if request.method == 'GET':
        return render_template('cliente_registro.html')
    token = session.get('sms_challenge_id')
    if not token:
        return 'Verifica tu teléfono por SMS antes de registrarte.', 400
    try:
        telefono = auth_challenges.normalize_phone(request.form.get('telefono'))
    except ValueError as exc:
        return str(exc), 400
    nombre = request.form.get('nombre', '').strip()
    apellidos = request.form.get('apellidos', '').strip()
    password = request.form.get('password', '')
    if not nombre or not apellidos or len(password) < 12:
        return 'Nombre, apellidos y contraseña de al menos 12 caracteres son obligatorios.', 400
    existente, _ = _customer_by_normalized_phone(telefono)
    if existente:
        return 'El teléfono ya está registrado.', 400
    ruta_foto = None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if not auth_challenges.consume_sms(cursor, token, telefono):
            conn.rollback()
            return 'La verificación SMS falta, expiró o ya fue utilizada.', 400
        foto = request.files.get('foto')
        if foto and foto.filename:
            ruta_foto = save_profile_image(foto, current_app.static_folder)
        execute_sp(
            cursor,
            'crm.sp_RegistrarClienteVerificado',
            (
                nombre,
                apellidos,
                telefono,
                generate_password_hash(password),
                request.form.get('genero'),
                request.form.get('fecha_nacimiento') or None,
                ruta_foto,
            ),
            fallback_sql="""INSERT INTO Clientes (Nombre, Apellidos, Telefono, PasswordHash, Genero,
                                     FechaNacimiento, RutaFotoPerfil, EsInvitado, NivelConfianzaID)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)""",
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if ruta_foto:
            from pathlib import Path
            (Path(current_app.static_folder) / ruta_foto).unlink(missing_ok=True)
        if isinstance(exc, ValueError):
            return str(exc), 400
        current_app.logger.exception('No se pudo completar el registro de cliente')
        return 'No se pudo completar el registro. Inténtalo de nuevo.', 503
    finally:
        conn.close()
    _clear_sms_session()
    cliente_nuevo, _ = Cliente.get_by_telefono(telefono)
    if cliente_nuevo:
        login_user(cliente_nuevo)
    return redirect(url_for('auth.cliente_inicio_exitoso'))


@auth_bp.route('/api/enviar_codigo_sms', methods=['POST'])
def enviar_codigo_sms():
    data = request.get_json(silent=True) or {}
    try:
        telefono = auth_challenges.normalize_phone(data.get('telefono'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    existente, _ = _customer_by_normalized_phone(telefono)
    if existente:
        return jsonify(error='Este teléfono ya está registrado'), 400
    account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    if not account_sid or not auth_token:
        return jsonify(error='El servicio SMS no está disponible. Inténtalo más tarde.'), 503
    token = None
    try:
        token, codigo = auth_challenges.issue_sms(telefono)
        Client(account_sid, auth_token).messages.create(
            to=telefono, from_=os.environ.get('TWILIO_FROM_NUMBER', '+17372212163'),
            body=f'Tu código de verificación para Panadería Amada es: {codigo}')
        auth_challenges.revoke(session.get('sms_challenge_id'))
        _clear_sms_session()
        session['sms_challenge_id'] = token
        return jsonify(mensaje='Código enviado exitosamente')
    except auth_challenges.ResendTooSoon as error:
        return jsonify(error=str(error)), 429, {'Retry-After': '60'}
    except Exception:
        if token:
            auth_challenges.revoke(token)
        # Provider exceptions may include message bodies and credentials.
        current_app.logger.warning('No se pudo enviar el mensaje de verificación SMS')
        return jsonify(error='No se pudo enviar el SMS. Inténtalo más tarde.'), 503


@auth_bp.route('/api/verificar_codigo_sms', methods=['POST'])
def verificar_codigo_sms():
    data = request.get_json(silent=True) or {}
    token = session.get('sms_challenge_id')
    if not token:
        return jsonify(error='No hay código pendiente de verificación'), 400
    try:
        telefono = auth_challenges.normalize_phone(data.get('telefono'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if auth_challenges.verify_sms(token, telefono, data.get('codigo')):
        return jsonify(mensaje='Teléfono verificado correctamente')
    return jsonify(error='Código incorrecto, expirado o utilizado.'), 400


@auth_bp.route('/cliente/inicio_exitoso')
@login_required
def cliente_inicio_exitoso():
    """Pantalla temporal de bienvenida tras crear cuenta."""
    return render_template('cliente_inicio_exitoso.html')


@auth_bp.route('/cliente/invitado')
def cliente_invitado():
    """Inicia sesión con el perfil de cliente invitado por defecto (ID=1)."""
    if current_user.is_authenticated:
        return redirect('/pos')

    cliente_invitado = Cliente.get_by_id(1)
    if cliente_invitado:
        login_user(cliente_invitado)
        return redirect('/pos')
    else:
        flash("No se pudo iniciar sesión como invitado.", "error")
        return redirect(url_for('auth.cliente_bienvenida'))
