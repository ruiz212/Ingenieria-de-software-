"""Servicio centralizado de Alertas de Seguridad y Errores por Correo SMTP.

Integra:
  1. Persistencia inmutable en [seguridad].[BitacoraErrores] vía Stored Procedure
     [seguridad].[sp_RegistrarErrorBD].
  2. Despacho de correos HTML/Texto por SMTP (STARTTLS / SSL) usando smtplib.
  3. Limitación de tasa (Rate-Limiting / Deduplicación) en ventana configurable
     para evitar tormentas de correos ante fallos repetitivos.
  4. Actualización automática de NotificadoSMTP = 1 mediante
     [seguridad].[sp_MarcarErrorNotificadoSMTP].
"""
from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
import html
import json
import logging
import os
import smtplib
import threading
import time
from typing import Any

from flask import current_app, has_app_context, has_request_context, request
from flask_login import current_user

logger = logging.getLogger(__name__)

_RATE_LIMIT_LOCK = threading.Lock()
_LAST_SENT_BY_KEY: dict[tuple[str, ...], float] = {}
_IN_FLIGHT: set[tuple[str, ...]] = set()
# Only explicit synchronous requests use these slots. Async requests enqueue in
# SQL and the external consumer delivers serially; no daemon per request.
_SEND_SLOTS = threading.BoundedSemaphore(4)


def reset_rate_limit_cache() -> None:
    """Limpia la caché de rate-limiting (útil para pruebas automatizadas)."""
    with _RATE_LIMIT_LOCK:
        _LAST_SENT_BY_KEY.clear()


def _normalize_recipients(raw_recipients: Any) -> list[str]:
    """Normaliza destinatarios desde lista, tupla, cadena JSON o texto separado por comas."""
    if raw_recipients is None:
        return []
    if isinstance(raw_recipients, (list, tuple, set)):
        out: list[str] = []
        for item in raw_recipients:
            out.extend(_normalize_recipients(item))
        return out
    if isinstance(raw_recipients, str):
        stripped = raw_recipients.strip()
        if not stripped:
            return []
        if stripped.startswith(('[', '"')):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                pass
            else:
                if isinstance(parsed, str):
                    return [r.strip() for r in parsed.split(',') if r.strip()]
                if isinstance(parsed, (list, tuple)):
                    return [str(r).strip() for r in parsed if str(r).strip()]
        return [r.strip() for r in stripped.split(',') if r.strip()]
    text = str(raw_recipients).strip()
    return [text] if text else []


def _should_allow_send(key: tuple[str, ...], window_seconds: int, force_send=False) -> bool:
    """Atomically reserve transient notifications which have no durable DB ID."""
    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        if key in _IN_FLIGHT:
            return False
        last_time = _LAST_SENT_BY_KEY.get(key)
        if not force_send and window_seconds > 0 and last_time is not None and (now - last_time) < window_seconds:
            return False
        # Transient-only fallback must not accumulate an unbounded process cache.
        for old_key, timestamp in list(_LAST_SENT_BY_KEY.items()):
            if now - timestamp >= max(window_seconds, 300):
                _LAST_SENT_BY_KEY.pop(old_key, None)
        if len(_LAST_SENT_BY_KEY) >= 4096:
            _LAST_SENT_BY_KEY.pop(next(iter(_LAST_SENT_BY_KEY)))
        _IN_FLIGHT.add(key)
        return True


def _record_successful_send(key: tuple[str, ...]) -> None:
    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        _LAST_SENT_BY_KEY[key] = now


def _extract_request_context() -> dict[str, Any]:
    ctx: dict[str, Any] = {
        'usuario_id': None,
        'username': None,
        'rol': None,
        'ip': None,
        'ruta_http': None,
    }
    if has_request_context():
        from app.services.request_context import client_ip
        ctx['ip'] = client_ip()
        ctx['ruta_http'] = request.path
        try:
            if current_user and getattr(current_user, 'is_authenticated', False):
                raw_id = getattr(current_user, 'id', None)
                ctx['usuario_id'] = int(raw_id) if raw_id is not None and str(raw_id).isdigit() else None
                ctx['username'] = getattr(current_user, 'username', None) or getattr(current_user, 'nombre', None)
                ctx['rol'] = getattr(current_user, 'rol_nombre', None)
        except Exception:
            pass
    return ctx


def _mask_sensitive_data(value: Any) -> Any:
    """Enmascara recursivamente claves sensibles en diccionarios y valores posicionales desconocidos en listas/tuplas."""
    sensitive_tokens = ('password', 'passwd', 'pass', 'secret', 'token', 'hash', 'totp', 'credential', 'authorization', 'cookie')
    if isinstance(value, dict):
        masked = {}
        for k, v in value.items():
            if any(tok in str(k).lower() for tok in sensitive_tokens):
                masked[k] = '***MASKED***'
            elif isinstance(v, (list, tuple)):
                masked[k] = [
                    _mask_sensitive_data(item) if isinstance(item, dict) else '***MASKED***'
                    for item in v
                ]
            else:
                masked[k] = _mask_sensitive_data(v)
        return masked
    if isinstance(value, (list, tuple)):
        return [
            _mask_sensitive_data(item) if isinstance(item, dict) else '***MASKED***'
            for item in value
        ]
    if isinstance(value, str):
        import re as _re
        if value.lstrip().startswith(('{', '[')):
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                pass
            else:
                return json.dumps(_mask_sensitive_data(decoded), ensure_ascii=False, default=str)
        return _re.sub(
            r'(?i)\b(password|passwd|secret|token|hash|totp)\s*([=:])\s*([^\s,;]+)',
            r'\1\2***MASKED***',
            value,
        )
    return value


def get_smtp_config(app_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = app_config if app_config is not None else (current_app.config if has_app_context() else {})
    enabled = cfg.get('SMTP_ENABLED', os.environ.get('SMTP_ENABLED', 'True').lower() in ('true', '1', 't', 'yes'))
    host = cfg.get('SMTP_HOST') or os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(cfg.get('SMTP_PORT') or os.environ.get('SMTP_PORT', '587'))
    use_tls = cfg.get('SMTP_USE_TLS', os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't', 'yes'))
    use_ssl = cfg.get('SMTP_USE_SSL', os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't', 'yes'))
    user = cfg.get('SMTP_USER') or os.environ.get('SMTP_USER', '')
    password = cfg.get('SMTP_PASSWORD') or os.environ.get('SMTP_PASSWORD', '')
    from_email = (
        cfg.get('SMTP_FROM_EMAIL')
        or cfg.get('SMTP_FROM')
        or os.environ.get('SMTP_FROM_EMAIL')
        or user
        or 'alertas@brajherscake.local'
    )
    raw_recipients = (
        cfg.get('SMTP_ALERT_RECIPIENTS')
        or cfg.get('SMTP_ADMIN_RECIPIENTS')
        or os.environ.get('SMTP_ALERT_RECIPIENTS', '')
    )
    recipients = _normalize_recipients(raw_recipients)
    if 'SMTP_RATE_LIMIT_SECONDS' in cfg:
        rate_limit = int(cfg['SMTP_RATE_LIMIT_SECONDS'])
    elif 'SMTP_RATE_LIMIT_MINUTES' in cfg:
        rate_limit = int(cfg['SMTP_RATE_LIMIT_MINUTES']) * 60
    else:
        rate_limit = int(os.environ.get('SMTP_RATE_LIMIT_SECONDS', '300'))
    async_mode = cfg.get('SMTP_ASYNC', os.environ.get('SMTP_ASYNC', 'False' if cfg.get('TESTING') else 'True').lower() in ('true', '1', 't', 'yes'))
    conn_str = cfg.get('SQL_SERVER_CONNECTION_STRING', '')
    testing = bool(cfg.get('TESTING', False))
    return {
        'enabled': bool(enabled),
        'host': host,
        'port': port,
        'use_tls': bool(use_tls),
        'use_ssl': bool(use_ssl),
        'user': user,
        'password': password,
        'from_email': from_email,
        'recipients': recipients,
        'rate_limit_seconds': rate_limit,
        'async': bool(async_mode),
        'connection_string': conn_str,
        'testing': testing,
    }


def build_alert_email(
    payload: dict[str, Any],
    recipients: list[str] | None = None,
    from_email: str | None = None,
) -> EmailMessage:
    if recipients is None or from_email is None:
        cfg = get_smtp_config()
        if recipients is None:
            recipients = cfg.get('recipients') or ['seguridad@brajherscake.local']
        if from_email is None:
            from_email = cfg.get('from_email') or 'alertas@brajherscake.local'

    severidad = str(payload.get('severidad') or 'ERROR').upper()
    origen = str(payload.get('origen') or 'SQL_SP')
    procedimiento = payload.get('procedimiento') or 'N/A'
    esquema = payload.get('esquema_origen') or 'N/A'
    numero_error = payload.get('numero_error')
    linea_error = payload.get('linea_error')
    mensaje = str(_mask_sensitive_data(str(payload.get('mensaje_error') or 'Error no especificado')))
    detalle = str(_mask_sensitive_data(str(payload.get('detalle_tecnico') or '')))
    username = payload.get('username') or 'Anónimo / Sistema'
    rol = payload.get('rol') or payload.get('rol_usuario') or 'N/A'
    ip = payload.get('ip') or payload.get('direccion_ip') or 'N/A'
    ruta = payload.get('ruta_http') or 'N/A'
    fecha_hora = payload.get('fecha_hora') or datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    error_id = payload.get('error_id')
    raw_params = payload.get('parametros_json')
    masked_params = _mask_sensitive_data(raw_params) if raw_params is not None else None
    params_str = (
        json.dumps(masked_params, ensure_ascii=False, default=str)
        if masked_params is not None and not isinstance(masked_params, str)
        else (str(masked_params) if masked_params is not None else '')
    )

    badge_colors = {
        'CRITICAL': '#991b1b',
        'ERROR': '#dc2626',
        'WARNING': '#d97706',
        'INFO': '#2563eb',
    }
    color = badge_colors.get(severidad, '#dc2626')

    subject = f"[ALERTA BD - {severidad}] Panadería Brajher's Cake — {origen} ({procedimiento})"
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = ', '.join(recipients)

    text_body = (
        f"ALERTA DE SEGURIDAD / BASE DE DATOS — PANADERÍA BRAJHER'S CAKE\n"
        f"================================================================\n"
        f"ID Bitácora:    #{error_id if error_id is not None else 'N/A'}\n"
        f"Fecha/Hora:     {fecha_hora}\n"
        f"Severidad:      {severidad}\n"
        f"Origen:         {origen}\n"
        f"Esquema / SP:   {esquema} / {procedimiento}\n"
        f"Código / Línea: {numero_error if numero_error is not None else 'N/A'} / L{linea_error if linea_error is not None else 'N/A'}\n"
        f"Usuario / Rol:  {username} ({rol})\n"
        f"Dirección IP:   {ip}\n"
        f"Ruta HTTP:      {ruta}\n\n"
        f"Mensaje del Error:\n{mensaje}\n\n"
        f"Parámetros (Enmascarados):\n{params_str or 'N/A'}\n\n"
        f"Detalle Técnico:\n{detalle or 'Sin detalle adicional'}\n"
    )
    msg.set_content(text_body)

    html_body = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"></head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; background:#f8fafc; padding:20px; color:#1e293b;">
  <div style="max-width:680px; margin:0 auto; background:#ffffff; border-radius:10px; border:1px solid #e2e8f0; overflow:hidden;">
    <div style="background:{color}; color:#ffffff; padding:16px 24px;">
      <h2 style="margin:0; font-size:18px;">Alerta de Seguridad y Base de Datos ({html.escape(severidad)})</h2>
      <p style="margin:4px 0 0; font-size:13px; opacity:0.9;">Panadería y Repostería Brajher's Cake — Monitor SMTP</p>
    </div>
    <div style="padding:24px;">
      <table style="width:100%; border-collapse:collapse; font-size:14px;">
        <tr><td style="padding:6px 0; font-weight:bold; width:160px;">ID Bitácora:</td><td>#{html.escape(str(error_id or 'N/A'))}</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Fecha y Hora:</td><td>{html.escape(str(fecha_hora))}</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Origen:</td><td>{html.escape(origen)}</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Esquema / Objeto:</td><td><code>{html.escape(str(esquema))}</code> / <code>{html.escape(str(procedimiento))}</code></td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Código SQL / Línea:</td><td>{html.escape(str(numero_error if numero_error is not None else 'N/A'))} / Línea {html.escape(str(linea_error if linea_error is not None else 'N/A'))}</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Usuario / Rol:</td><td>{html.escape(str(username))} ({html.escape(str(rol))})</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Dirección IP:</td><td>{html.escape(str(ip))}</td></tr>
        <tr><td style="padding:6px 0; font-weight:bold;">Ruta HTTP:</td><td><code>{html.escape(str(ruta))}</code></td></tr>
      </table>
      <div style="margin-top:18px; padding:14px; background:#fef2f2; border-left:4px solid {color}; border-radius:4px;">
        <div style="font-weight:bold; margin-bottom:6px; color:#7f1d1d;">Mensaje del Evento:</div>
        <div style="font-family:Consolas, monospace; font-size:13px; white-space:pre-wrap;">{html.escape(mensaje)}</div>
      </div>
      {f'<div style="margin-top:14px; padding:12px; background:#f8fafc; border-radius:4px; font-family:Consolas, monospace; font-size:12px; white-space:pre-wrap;"><strong>Parámetros:</strong> {html.escape(params_str)}</div>' if params_str else ''}
      {f'<div style="margin-top:14px; padding:12px; background:#f1f5f9; border-radius:4px; font-family:Consolas, monospace; font-size:12px; white-space:pre-wrap;">{html.escape(detalle)}</div>' if detalle else ''}
    </div>
  </div>
</body>
</html>"""
    msg.add_alternative(html_body, subtype='html')
    return msg


def send_smtp_message(msg: EmailMessage, smtp_cfg: dict[str, Any]) -> bool:
    """Envía un EmailMessage usando smtplib (soporta STARTTLS y SSL)."""
    if not smtp_cfg.get('enabled', True):
        return False
    recipients = _normalize_recipients(smtp_cfg.get('recipients'))
    if not recipients:
        return False

    host = smtp_cfg['host']
    port = smtp_cfg['port']
    use_ssl = smtp_cfg.get('use_ssl', False)
    use_tls = smtp_cfg.get('use_tls', True)
    user = smtp_cfg.get('user') or ''
    password = smtp_cfg.get('password') or ''

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=10) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    return True


def _open_standalone_sql_connection(smtp_cfg: dict[str, Any]):
    conn_str = smtp_cfg.get('connection_string') or ''
    if not conn_str:
        return None
    import pyodbc
    if smtp_cfg.get('testing'):
        from app.qa_safety import connect_qa
        return connect_qa(pyodbc.connect, conn_str)
    return pyodbc.connect(conn_str)


def record_error_in_db(payload: dict[str, Any], smtp_cfg: dict[str, Any] | None = None, connection=None) -> int | None:
    """Registra el error en [seguridad].[BitacoraErrores] ejecutando [seguridad].[sp_RegistrarErrorBD]."""
    cfg = smtp_cfg or get_smtp_config()
    own_conn = False
    conn = connection
    try:
        if conn is None:
            conn = _open_standalone_sql_connection(cfg)
            own_conn = True
        if conn is None:
            return None

        cursor = conn.cursor()
        params_json = payload.get('parametros_json')
        if params_json is not None and not isinstance(params_json, str):
            params_json = json.dumps(params_json, ensure_ascii=False, default=str)

        sql = """
        SET NOCOUNT ON;
        DECLARE @OutID BIGINT;
        EXEC [seguridad].[sp_RegistrarErrorBD]
            @Origen = ?,
            @Severidad = ?,
            @NumeroError = ?,
            @EstadoError = ?,
            @LineaError = ?,
            @Procedimiento = ?,
            @EsquemaOrigen = ?,
            @MensajeError = ?,
            @DetalleTecnico = ?,
            @ParametrosJSON = ?,
            @UsuarioID = ?,
            @Username = ?,
            @RolAplicacion = ?,
            @DireccionIP = ?,
            @RutaHTTP = ?,
            @ErrorRegistradoID = @OutID OUTPUT;
        SELECT @OutID AS ErrorID;
        """
        cursor.execute(
            sql,
            str(payload.get('origen') or 'SQL_SP')[:30],
            str(payload.get('severidad') or 'ERROR')[:15],
            payload.get('numero_error'),
            payload.get('estado_error'),
            payload.get('linea_error'),
            payload.get('procedimiento'),
            payload.get('esquema_origen'),
            str(payload.get('mensaje_error') or 'Error no especificado')[:2000],
            payload.get('detalle_tecnico'),
            params_json,
            payload.get('usuario_id'),
            payload.get('username'),
            payload.get('rol'),
            payload.get('ip'),
            payload.get('ruta_http'),
        )
        row = cursor.fetchone()
        error_id = int(row[0]) if row and row[0] is not None else None
        if own_conn:
            conn.commit()
        return error_id
    except Exception as exc:
        logger.debug("No se pudo persistir en BitacoraErrores: %s", exc)
        if own_conn and conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def mark_error_notified(error_id: int, smtp_cfg: dict[str, Any] | None = None, connection=None) -> bool:
    """Marca NotificadoSMTP = 1 en [seguridad].[BitacoraErrores] vía SP."""
    if not error_id:
        return False
    cfg = smtp_cfg or get_smtp_config()
    own_conn = False
    conn = connection
    try:
        if conn is None:
            conn = _open_standalone_sql_connection(cfg)
            own_conn = True
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("SET NOCOUNT ON; EXEC [seguridad].[sp_MarcarErrorNotificadoSMTP] @ErrorID = ?", int(error_id))
        if own_conn:
            conn.commit()
        return True
    except Exception as exc:
        logger.debug("No se pudo marcar NotificadoSMTP para ErrorID=%s: %s", error_id, exc)
        return False
    finally:
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _outbox_call(smtp_cfg, sql, params=(), connection=None):
    """Execute one short reservation transaction, committing before SMTP I/O."""
    own_conn = connection is None
    conn = connection or _open_standalone_sql_connection(smtp_cfg)
    if conn is None:
        raise RuntimeError('SMTP outbox requires SQL_SERVER_CONNECTION_STRING')
    try:
        cursor = conn.cursor()
        cursor.execute(sql, *params)
        row = cursor.fetchone() if cursor.description else None
        result = dict(zip((c[0] for c in cursor.description), row)) if row else None
        if own_conn:
            conn.commit()
        return result
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()


def _enqueue_error(error_id, smtp_cfg, payload=None, connection=None) -> bool:
    payload = payload or {}
    raw_override = (
        payload.get('override_recipients')
        if payload.get('override_recipients') is not None
        else (payload.get('destinatarios') if payload.get('destinatarios') is not None else payload.get('destinatario'))
    )
    recipients = _normalize_recipients(raw_override)
    try:
        result = _outbox_call(smtp_cfg,
            'SET NOCOUNT ON; EXEC seguridad.sp_EncolarAlertaSMTP @ErrorID=?, @DestinatariosJSON=?, @Forzar=?',
            (int(error_id), json.dumps(recipients) if recipients else None,
             bool(payload.get('force_send'))), connection)
        return bool(result and result.get('Encolada'))
    except Exception as exc:
        # The immutable log already exists; a later consumer seeds missing rows.
        logger.warning('No se pudo encolar alerta SMTP ErrorID=%s: %s', error_id, exc)
        return False


def _claim_alert(smtp_cfg, error_id=None, connection=None, seed_batch=20):
    return _outbox_call(smtp_cfg,
        'SET NOCOUNT ON; EXEC seguridad.sp_ReclamarAlertaSMTP @ErrorID=?, @VentanaSegundos=?, @LeaseSegundos=?, @SembrarLote=?',
        (error_id, max(0, min(int(smtp_cfg.get('rate_limit_seconds', 300)), 86400)),
         300, seed_batch), connection)


def _complete_alert(claim, smtp_cfg, sent, connection=None):
    result = _outbox_call(smtp_cfg,
        'SET NOCOUNT ON; EXEC seguridad.sp_FinalizarAlertaSMTP @ErrorID=?, @Token=?, @Enviado=?',
        (claim['ID'], str(claim['ClaimToken']), bool(sent)), connection)
    return bool(result and result.get('Finalizada'))


def _claim_payload(claim):
    fields = {'ID': 'error_id', 'FechaHora': 'fecha_hora', 'Origen': 'origen',
              'Severidad': 'severidad', 'NumeroError': 'numero_error',
              'EstadoError': 'estado_error', 'LineaError': 'linea_error',
              'Procedimiento': 'procedimiento', 'EsquemaOrigen': 'esquema_origen',
              'MensajeError': 'mensaje_error', 'DetalleTecnico': 'detalle_tecnico',
              'ParametrosJSON': 'parametros_json', 'UsuarioID': 'usuario_id',
              'Username': 'username', 'RolAplicacion': 'rol', 'DireccionIP': 'ip',
              'RutaHTTP': 'ruta_http'}
    return {target: claim.get(source) for source, target in fields.items()}


def _deliver_claim(claim, smtp_cfg, connection=None):
    sent = False
    completed = False
    try:
        payload = _claim_payload(claim)
        raw_row_recipients = (
            claim.get('DestinatariosJSON')
            or claim.get('Destinatario')
            or claim.get('destinatarios')
            or claim.get('destinatario')
        )
        row_recipients = _normalize_recipients(raw_row_recipients)
        recipients = row_recipients if row_recipients else _normalize_recipients(smtp_cfg.get('recipients'))
        if recipients:
            cfg = dict(smtp_cfg, recipients=recipients)
            sent = bool(send_smtp_message(build_alert_email(payload, recipients, cfg.get('from_email') or 'alertas@brajherscake.local'), cfg))
        else:
            sent = False
    except Exception as exc:
        logger.warning('Fallo al enviar alerta SMTP ErrorID=%s: %s', claim['ID'], exc)
    finally:
        # On failure release the shared reservation and delay this row's retry.
        # An accepted email followed by a failed ACK remains retryable: at least once.
        try:
            completed = _complete_alert(claim, smtp_cfg, sent, connection)
        except Exception as exc:
            logger.warning('No se pudo confirmar alerta SMTP ErrorID=%s: %s', claim['ID'], exc)
    return {'error_id': claim['ID'], 'sent': sent, 'rate_limited': False,
            'queued': not (sent and completed), 'acknowledged': completed}


def _dispatch_worker(payload: dict[str, Any], smtp_cfg: dict[str, Any], connection=None) -> dict[str, Any]:
    error_id = payload.get('error_id')
    if error_id is None and payload.get('persist_in_db', True):
        error_id = record_error_in_db(payload, smtp_cfg, connection=connection)
        payload['error_id'] = error_id
    queued = bool(error_id is not None and _enqueue_error(error_id, smtp_cfg, payload, connection))
    result = {'error_id': error_id, 'sent': False, 'rate_limited': False, 'queued': queued}
    override_recips = _normalize_recipients(
        payload.get('override_recipients')
        if payload.get('override_recipients') is not None
        else (payload.get('destinatarios') if payload.get('destinatarios') is not None else payload.get('destinatario'))
    )
    recipients = override_recips if override_recips else _normalize_recipients(smtp_cfg.get('recipients'))
    # The caller owns this transaction. SMTP must wait until its explicit commit
    # makes the event visible to the independent consumer.
    if connection is not None:
        return result
    if not smtp_cfg.get('enabled', True) or not recipients:
        return result
    if not _SEND_SLOTS.acquire(blocking=False):
        return result
    try:
        if error_id is not None:
            if not queued:
                return result
            claim = _claim_alert(smtp_cfg, error_id, connection, seed_batch=0)
            if claim is None:
                result['rate_limited'] = True
                return result
            return _deliver_claim(claim, smtp_cfg, connection)

        # Explicit nonpersistent events / DB outage fallback. Only SQL-backed IDs
        # offer cross-process suppression and restart recovery.
        has_proc_or_num = bool(payload.get('procedimiento') or payload.get('numero_error'))
        key = (str(payload.get('origen') or 'SQL_SP'), str(payload.get('numero_error') or ''),
               str(payload.get('procedimiento') or ''),
               '' if has_proc_or_num else str(payload.get('mensaje_error') or '')[:120])
        if not _should_allow_send(key, int(smtp_cfg.get('rate_limit_seconds', 300)), payload.get('force_send', False)):
            result['rate_limited'] = True
            return result
        try:
            result['sent'] = bool(send_smtp_message(build_alert_email(payload, recipients, smtp_cfg['from_email']),
                                                   dict(smtp_cfg, recipients=recipients)))
            if result['sent']:
                _record_successful_send(key)
        except Exception as exc:
            logger.warning('Fallo al enviar alerta SMTP: %s', exc)
        finally:
            with _RATE_LIMIT_LOCK:
                _IN_FLIGHT.discard(key)
        return result
    except Exception as exc:
        logger.warning('No se pudo reservar alerta SMTP ErrorID=%s: %s', error_id, exc)
        result['error'] = 'outbox_unavailable'
        return result
    finally:
        _SEND_SLOTS.release()


def retry_pending_alerts(max_batch: int = 20, smtp_cfg: dict[str, Any] | None = None,
                         connection=None) -> dict[str, Any]:
    """Consume a bounded durable batch; each short claim is committed before I/O.

    Transport requires independent committed reservations. Caller-owned business
    connections are rejected, never implicitly committed.
    """
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 100:
        raise ValueError('SMTP max_batch debe estar entre 1 y 100')
    if connection is not None:
        raise ValueError('SMTP consumer requires connection=None; caller owns transaction')
    cfg = smtp_cfg or get_smtp_config()
    stats = {'attempted': 0, 'delivered': 0, 'failed': 0, 'errors': 0}
    if not cfg.get('enabled', True):
        return stats
    for _ in range(max_batch):
        if not _SEND_SLOTS.acquire(blocking=False):
            break
        try:
            claim = _claim_alert(cfg, connection=connection, seed_batch=max_batch)
            if not claim:
                break
            stats['attempted'] += 1
            result = _deliver_claim(claim, cfg, connection)
            if result['sent'] and result['acknowledged']:
                stats['delivered'] += 1
            else:
                stats['failed'] += 1
        except Exception as exc:
            stats['errors'] += 1
            logger.warning('No se pudo procesar outbox SMTP: %s', exc)
            break
        finally:
            _SEND_SLOTS.release()
    return stats


def notify_error(
    mensaje_error: str,
    *,
    origen: str = 'SQL_SP',
    severidad: str = 'ERROR',
    numero_error: int | None = None,
    estado_error: int | None = None,
    linea_error: int | None = None,
    procedimiento: str | None = None,
    esquema_origen: str | None = None,
    detalle_tecnico: str | None = None,
    parametros_json: Any = None,
    usuario_id: int | None = None,
    username: str | None = None,
    rol: str | None = None,
    ip: str | None = None,
    ruta_http: str | None = None,
    error_id: int | None = None,
    persist_in_db: bool = True,
    async_send: bool | None = None,
    force_send: bool = False,
    override_recipients: list[str] | str | None = None,
    connection=None,
) -> dict[str, Any]:
    """Registra un error/evento de seguridad en BD y despacha alerta por correo SMTP."""
    req_ctx = _extract_request_context()
    smtp_cfg = get_smtp_config()
    normalized_override = _normalize_recipients(override_recipients) or None

    payload = {
        'origen': origen,
        'severidad': severidad,
        'numero_error': numero_error,
        'estado_error': estado_error,
        'linea_error': linea_error,
        'procedimiento': procedimiento,
        'esquema_origen': esquema_origen,
        'mensaje_error': _mask_sensitive_data(mensaje_error),
        'detalle_tecnico': _mask_sensitive_data(detalle_tecnico),
        'parametros_json': _mask_sensitive_data(parametros_json) if parametros_json is not None else None,
        'usuario_id': usuario_id if usuario_id is not None else req_ctx['usuario_id'],
        'username': username if username is not None else req_ctx['username'],
        'rol': rol if rol is not None else req_ctx['rol'],
        'ip': ip if ip is not None else req_ctx['ip'],
        'ruta_http': ruta_http if ruta_http is not None else req_ctx['ruta_http'],
        'fecha_hora': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'error_id': error_id,
        'persist_in_db': persist_in_db,
        'force_send': force_send,
        'override_recipients': normalized_override,
    }

    use_async = smtp_cfg['async'] if async_send is None else async_send
    if use_async and connection is None:
        # Durability precedes acknowledgement. No executor queue or daemon can
        # drop an event on saturation or interpreter shutdown.
        if error_id is None and persist_in_db:
            error_id = record_error_in_db(payload, smtp_cfg)
            payload['error_id'] = error_id
        if error_id is None:
            # SQL outage or an explicitly transient alert: preserve notification
            # capability with bounded synchronous transport, without a second DB
            # write or an unbounded thread/queue. No durable recovery is possible.
            payload['persist_in_db'] = False
            return _dispatch_worker(payload, smtp_cfg)
        queued = bool(error_id is not None and _enqueue_error(error_id, smtp_cfg, payload))
        return {'error_id': error_id, 'sent': False, 'queued': queued, 'rate_limited': False}

    return _dispatch_worker(payload, smtp_cfg, connection=connection)
