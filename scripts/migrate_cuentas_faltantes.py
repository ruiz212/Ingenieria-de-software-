import pyodbc
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def migrate():
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    print(f"Conectando a {conn_str}...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Insertar 1103 Bancos
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE Codigo = '1103'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('1103', 'Bancos', 'Activo', 'Activo Circulante', 'Deudora')")
            print("Cuenta 1103 agregada.")

        # Insertar 2102 IVA por Pagar
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE Codigo = '2102'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('2102', 'IVA por Pagar', 'Pasivo', 'Pasivo Circulante', 'Acreedora')")
            print("Cuenta 2102 agregada.")
            
        conn.commit()
        print("Migración completada exitosamente.")
    except Exception as e:
        print(f"Error durante la migración: {e}")

if __name__ == "__main__":
    migrate()
