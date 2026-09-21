import os
import secrets

class Config:
    SQL_SERVER_CONNECTION_STRING = os.environ.get('DB_CONNECTION_STRING') or r'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
    
    # Seguridad de Sesión
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-panaderia-2026'
    SESSION_COOKIE_HTTPONLY = True
    # En desarrollo local (HTTP) SECURE debe ser False, pero en prod (HTTPS) debe ser True. 
    # Lo dejamos False para pruebas locales, cambiar a True para producción.
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 horas de turno

