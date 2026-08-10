import pyodbc
from werkzeug.security import generate_password_hash


conn_str = r'DRIVER={ODBC Driver 18 for SQL Server};SERVER=DESKTOP-A45EBFM;DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

# Set password '123456' for everyone
new_hash = generate_password_hash('123456')
cursor.execute("UPDATE Usuarios SET PasswordHash = ?", new_hash)
print("Contraseñas actualizadas a '123456'")
conn.close()
