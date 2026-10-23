import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    SQL_SERVER_CONNECTION_STRING = os.environ.get('DB_CONNECTION_STRING') or (
        r'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;'
        r'DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
    )

    # Seguridad de Sesión
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    # En desarrollo local (HTTP) SECURE debe ser False, pero en prod (HTTPS) debe ser True.
    # Usamos una variable de entorno para que Azure lo fuerce a True.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ['true', '1', 't']
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 horas de turno
    WTF_CSRF_TIME_LIMIT = 28800  # 8 horas de turno (evita vencimientos prematuros)
    SESSION_REFRESH_EACH_REQUEST = False  # Solo el ping posterior a actividad renueva el vencimiento.

    # Configure the actual reverse-proxy peer ranges in staging/production.
    # Empty means forwarded headers cannot override the socket peer.
    TRUSTED_PROXY_CIDRS = tuple(value.strip() for value in os.environ.get('TRUSTED_PROXY_CIDRS', '').split(',') if value.strip())
    PROXY_X_FOR_HOPS = int(os.environ.get('PROXY_X_FOR_HOPS', '1'))

    # Configuración de Alertas de Seguridad y Errores por Correo SMTP
    SMTP_ENABLED = os.environ.get('SMTP_ENABLED', 'True').lower() in ['true', '1', 't', 'yes']
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'True').lower() in ['true', '1', 't', 'yes']
    SMTP_USE_SSL = os.environ.get('SMTP_USE_SSL', 'False').lower() in ['true', '1', 't', 'yes']
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL') or os.environ.get('SMTP_USER') or 'alertas@brajherscake.local'
    SMTP_ALERT_RECIPIENTS = os.environ.get('SMTP_ALERT_RECIPIENTS', '')
    SMTP_RATE_LIMIT_SECONDS = int(os.environ.get('SMTP_RATE_LIMIT_SECONDS', '300'))
    SMTP_ASYNC = os.environ.get('SMTP_ASYNC', 'True').lower() in ['true', '1', 't', 'yes']
