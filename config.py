import os

class Config:
    # Reemplazar con la cadena de conexión real a SQL Server
    # Ejemplo: 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=PanaderiaDB;UID=user;PWD=password'
    SQL_SERVER_CONNECTION_STRING = os.environ.get('DB_CONNECTION_STRING') or 'DRIVER={SQL Server};SERVER=localhost;DATABASE=PanaderiaDB;Trusted_Connection=yes;'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-desarrollo'
