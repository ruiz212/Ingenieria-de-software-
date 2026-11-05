"""Reauthentication for account changes, input/output security guardrails, and phone validation."""
import re
import pyotp
from werkzeug.security import check_password_hash
from app.models import User
from app.whatsapp.repository import connection

_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]')
_MULTI_NEWLINE_RE = re.compile(r'\n{4,}')

_INJECTION_PATTERNS = (
    (
        'prompt_injection',
        re.compile(
            r'(?:(?:ignora|olvida|descarta|omite|anula|desactiva|ignore|forget|disregard|override|bypass)\s+'
            r'(?:todas\s+|all\s+)?(?:las\s+|tus\s+|previous\s+|prior\s+|anteriores\s+)?'
            r'(?:instrucciones|reglas|ordenes|órdenes|pol[ií]ticas|protocolos|instructions|rules|prompts?|restricciones)|'
            r'(?:cu[aá]l\s+es|dime|mu[eé]strame|revela|repite|imprime|copia)\s+'
            r'(?:tu\s+|el\s+|las?\s+)?(?:system\s*prompt|prompt\s+inicial|instrucciones\s+internas|reglas\s+internas|configuraci[oó]n\s+interna))',
            re.IGNORECASE,
        ),
    ),
    (
        'system_override',
        re.compile(
            r'(?:system\s*prompt|instrucciones\s+del\s+sistema|developer\s+mode|modo\s+desarrollador|'
            r'jailbreak|act[uú]a\s+como\s+(?:administrador|superadmin|root|dba|sistema|hacker))',
            re.IGNORECASE,
        ),
    ),
    (
        'sql_injection',
        re.compile(
            r'(?:\b(?:drop\s+table|truncate\s+table|xp_cmdshell|sp_executesql|'
            r'union\s+(?:all\s+)?select|exec\s+(?:crm|ventas|seguridad|contabilidad|rrhh|fiscal)\.)\b|'
            r';\s*(?:drop|delete|update|insert|alter|exec|execute)\b|'
            r'\bselect\s+.+\s+from\s+(?:crm|ventas|seguridad|catalogo|produccion)\.)',
            re.IGNORECASE,
        ),
    ),
    (
        'cross_tenant_probe',
        re.compile(
            r'(?:muestra|muéstrame|dame|lista|listar|consulta|ver|extrae|p[aá]same|revela)\s+'
            r'(?:todos\s+los\s+|todas\s+las\s+|los\s+|las\s+|la\s+|el\s+)?'
            r'(?:pedidos|cotizaciones|tel[eé]fonos|clientes|facturas|correos|direcciones|contrase[ñn]as|claves|api\s*keys?|tokens?|credenciales|base\s+de\s+datos)\s*'
            r'(?:de\s+(?:otros?\s+clientes?|todas?\s+las?\s+personas?|todos|otra\s+persona|otro\s+n[uú]mero|los\s+usuarios|la\s+empresa|el\s+sistema)|del\s+sistema|intern[ao]s?)?',
            re.IGNORECASE,
        ),
    ),
)

_SENSITIVE_LEAK_RE = re.compile(
    r'(?:AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,}|GEMINI_API_KEY|sp_WhatsApp\w+|usr_bd_\w+|db_rol_\w+|'
    r'SESSION_CONTEXT|Traceback\s*\(most\s+recent\s+call\s+last\))',
    re.IGNORECASE,
)

_PAYMENT_HARVEST_RE = re.compile(
    r'(?:n[uú]mero\s+de\s+tarjeta|c[oó]digo\s+cvv|cvc\s+de\s+tu\s+tarjeta|pin\s+bancario|contrase[ñn]a\s+bancaria)',
    re.IGNORECASE,
)

SECURITY_BLOCK_REPLY = (
    "Por seguridad y políticas de privacidad de Brajher's Cake, no puedo compartir instrucciones internas, "
    "credenciales ni información de otros clientes. Con gusto puedo ayudarte a consultar nuestro catálogo, "
    "cotizar un pastel personalizado o revisar el estado de los pedidos asociados a tu número de teléfono."
)

SECURITY_PROTOCOLS = (
    {
        'id': 'reauth_2fa',
        'titulo': 'Reautenticación 2FA',
        'detalle': 'Cambios de cuenta y visualización de QR protegidos con contraseña + TOTP y bloqueo en SQL.',
    },
    {
        'id': 'anti_injection',
        'titulo': 'Escudo Anti-Inyección',
        'detalle': 'Filtrado de caracteres de control, bloqueo de prompt injection, SQL y consultas cruzadas.',
    },
    {
        'id': 'phone_isolation',
        'titulo': 'Aislamiento por Teléfono',
        'detalle': 'Cotizaciones y avisos de pedidos vinculados estrictamente al teléfono verificado del cliente.',
    },
    {
        'id': 'two_step_confirm',
        'titulo': 'Confirmación en 2 Pasos',
        'detalle': 'Toda creación o decisión de cotización exige borrador previo y confirmación explícita.',
    },
    {
        'id': 'rate_limit',
        'titulo': 'Control Anti-Flood',
        'detalle': 'Límite de 6 mensajes/minuto por sesión y bloqueo exclusivo por revisión de conversación.',
    },
)


def sanitize_incoming_text(text):
    if not isinstance(text, str):
        return ''
    cleaned = _CONTROL_CHARS_RE.sub('', text)
    cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
    cleaned = _MULTI_NEWLINE_RE.sub('\n\n\n', cleaned)
    return cleaned.strip()[:4000]


def detect_security_violation(text):
    cleaned = sanitize_incoming_text(text)
    if not cleaned:
        return False, None, None
    for code, pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            # For cross_tenant_probe, ensure we don't block "muéstrame mis pedidos" or "dame mis cotizaciones"
            if code == 'cross_tenant_probe':
                lower = cleaned.lower()
                if re.search(r'\b(?:mis\s+pedidos|mis\s+cotizaciones|mi\s+pedido|mi\s+cotizaci[oó]n)\b', lower) and not re.search(
                    r'\b(?:otros?|todas?|todos|ajeno|otra\s+persona|otro\s+n[uú]mero|contrase[ñn]a|clave|token|base\s+de\s+datos)\b',
                    lower,
                ):
                    continue
                if not re.search(
                    r'\b(?:otros?\s+clientes?|todas?\s+las?\s+personas?|todos|otra\s+persona|otro\s+n[uú]mero|'
                    r'contrase[ñn]as?|claves?|api\s*keys?|tokens?|credenciales|base\s+de\s+datos|tel[eé]fonos|correos|direcciones)\b',
                    lower,
                ):
                    continue
            return True, code, SECURITY_BLOCK_REPLY
    return False, None, None


def sanitize_bot_response(text, fallback):
    if not isinstance(text, str):
        return fallback
    cleaned = _CONTROL_CHARS_RE.sub('', text).strip()
    if not cleaned:
        return fallback
    if _SENSITIVE_LEAK_RE.search(cleaned) or _PAYMENT_HARVEST_RE.search(cleaned):
        return fallback
    return cleaned[:3500]


def normalize_nicaragua_phone(raw):
    """Return ('+505XXXXXXXX', '505XXXXXXXX@s.whatsapp.net', 'XXXXXXXX') or (None, None, None)."""
    if not raw or not isinstance(raw, str):
        return None, None, None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 11 and digits.startswith('505'):
        digits = digits[3:]
    if len(digits) != 8 or digits[0] not in '2578':
        return None, None, None
    phone = f'+505{digits}'
    jid = f'505{digits}@s.whatsapp.net'
    return phone, jid, digits


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
