"""Reauthentication for account changes, input/output security guardrails, and phone validation."""
import re
import unicodedata
import pyotp
from werkzeug.security import check_password_hash
from app.models import User
from app.whatsapp.repository import connection

_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]')
_MULTI_NEWLINE_RE = re.compile(r'\n{4,}')

_ROLE_SPOOF_RE = re.compile(
    r'\b(?:yo\s+)?(?:soy|habla)\s+(?:la\s+|el\s+|un[ao]?\s+)?'
    r'(?:due[ñn][oa]|propietari[oa]|administrador(?:a)?|superadmin(?:istrador)?|'
    r'gerente|jef[ea]|encargad[oa]\s+del?\s+sistema|programador(?:a)?|desarrollador(?:a)?|'
    r'soporte\s+t[eé]cnico|auditor(?:a)?|contador(?:a)?)\b',
    re.IGNORECASE,
)

_BAKERY_CONTEXT_RE = re.compile(
    r'\b(?:pastel(?:es|er[ií]a)?|queque(?:s)?|torta(?:s)?|pan(?:es|ader[ií]a)?|reposter[ií]a|'
    r'postre(?:s)?|galleta(?:s)?|dona(?:s)?|concha(?:s)?|bolillo(?:s)?|milanesa|pa[ñn]uelito|'
    r'selva\s+negra|tres\s+leches|chocolate|vainilla|caf[eé]|gaseosa|bebida(?:s)?|'
    r'cotizaci[oó]n(?:es)?|cotizar|pedido(?:s)?|encargo(?:s)?|factura(?:s)?|fac-\d+|cot-\d+|'
    r'cat[aá]logo|men[uú]|precio(?:s)?|horario(?:s)?|entrega|retiro|sucursal|tienda|'
    r'adelanto|saldo|libra(?:s)?|porci[oó]n(?:es)?|pisos?|relleno|cobertura|fondant|'
    r'chantilly|buttercream|cumplea[ñn]os|boda|evento|foto|imagen|referencia|inspiraci[oó]n|'
    r'brajher|amada|humano|confirmar|cancelar|avisos)\b',
    re.IGNORECASE,
)

_OFF_TOPIC_RE = re.compile(
    r'(?:\b(?:ra[ií]z\s+cuadrada|teorema\s+de|ecuaci[oó]n|derivada|integral\s+de|'
    r'primera\s+guerra\s+mundial|segunda\s+guerra\s+mundial|revoluci[oó]n\s+francesa|'
    r'imperio\s+romano|capital\s+de\s+[a-záéíóúñ]+|presidente\s+de|qui[eé]n\s+descubri[oó]|'
    r'qui[eé]n\s+invent[oó]|qui[eé]n\s+gan[oó]|escribe\s+un\s+(?:poema|ensayo|c[oó]digo|script|programa)|'
    r'en\s+(?:python|javascript|java|c\+\+|html)|traduce\s+al\s+(?:ingl[eé]s|franc[eé]s|alem[aá]n)|'
    r'hor[oó]scopo|pron[oó]stico\s+del\s+clima|receta\s+m[eé]dica|'
    r'(?:resuelve|hazme)\s+(?:esta|mi)?\s*tarea|tarea\s+de\s+[a-záéíóúñ]+)\b|'
    r'\bcu[aá]nto\s+es\s+\d+\s*(?:[\+\-\*\/x]|m[aá]s|menos|por|entre)\s*\d+)',
    re.IGNORECASE,
)

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
    "cotizar un pastel personalizado o revisar el estado de un pedido validando el nombre del titular y su código."
)

ROLE_SPOOF_REPLY = (
    "Por seguridad y políticas de privacidad de Brajher's Cake, no puedo validar cargos administrativos "
    "ni de propiedad por WhatsApp. Este canal es exclusivamente para atención al cliente; las gestiones "
    "administrativas solo se realizan en el sistema interno con autenticación de dos factores (2FA). "
    "Con gusto puedo atenderte como cliente para ver nuestro catálogo, cotizar un pastel o rastrear un pedido."
)

OFF_TOPIC_REPLY = (
    "Soy el asistente virtual exclusivo de Brajher's Cake (Panadería Amada) en Managua. "
    "Solo puedo responder consultas sobre nuestro catálogo de panadería y repostería, cotizaciones de "
    "pasteles personalizados y seguimiento verificado de pedidos. ¿En qué te puedo colaborar hoy?"
)

_STOPWORDS_NAME = frozenset({
    'de', 'del', 'la', 'las', 'el', 'los', 'sr', 'sra', 'srta', 'don', 'dona',
    'lic', 'ing', 'dr', 'dra', 'arq', 'prof', 'bro', 'cliente', 'invitado', 'general',
})

SECURITY_PROTOCOLS = (
    {
        'id': 'reauth_2fa',
        'titulo': 'Reautenticación 2FA',
        'detalle': 'Cambios de cuenta y visualización de QR protegidos con contraseña + TOTP y bloqueo en SQL.',
    },
    {
        'id': 'anti_injection',
        'titulo': 'Escudo Anti-Inyección',
        'detalle': 'Filtrado de caracteres de control, bloqueo de prompt injection, SQL, suplantación y consultas cruzadas.',
    },
    {
        'id': 'order_verification',
        'titulo': 'Validación de Titular y Pedido',
        'detalle': 'Exige verificar nombre del titular y código/factura antes de compartir el estado o saldo de un pedido.',
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


def _normalize_name_tokens(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    decomposed = unicodedata.normalize('NFKD', value.strip().lower())
    ascii_only = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    tokens = re.findall(r'[a-z]{3,}', ascii_only)
    return [t for t in tokens if t not in _STOPWORDS_NAME]


def verify_holder_name(provided_name: str, record_name: str) -> bool:
    """Return True only when the caller provides a real name that matches the order holder."""
    provided_tokens = _normalize_name_tokens(provided_name)
    record_tokens = _normalize_name_tokens(record_name)
    if not provided_tokens or not record_tokens:
        return False
    overlap = set(provided_tokens) & set(record_tokens)
    if not overlap:
        return False
    if len(record_tokens) >= 2 and len(provided_tokens) >= 2:
        return len(overlap) >= 1 and provided_tokens[0] in record_tokens
    return True


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
    if _ROLE_SPOOF_RE.search(cleaned):
        return True, 'role_spoofing', ROLE_SPOOF_REPLY
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
    if _OFF_TOPIC_RE.search(cleaned) and not _BAKERY_CONTEXT_RE.search(cleaned):
        return True, 'off_topic', OFF_TOPIC_REPLY
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
