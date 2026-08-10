import pyodbc
import os
# pyrefly: ignore [missing-import]
from werkzeug.security import generate_password_hash

def try_connect_and_setup():
    drivers = [driver for driver in pyodbc.drivers() if 'SQL Server' in driver or 'ODBC Driver' in driver]
    if not drivers:
        print("No SQL Server ODBC drivers found.")
        return False
        
    driver = drivers[-1] # Usually the most recent ODBC driver
    print(f"Using driver: {driver}")
    
    servers = [r'DESKTOP-A45EBFM']
    
    for server in servers:
        try:
            print(f"Trying to connect to {server}...")
            # Connect to master to create DB
            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=30)
            cursor = conn.cursor()
            
            # Check if DB exists
            cursor.execute("SELECT name FROM master.dbo.sysdatabases WHERE name = N'PanaderiaDB'")
            if not cursor.fetchone():
                print("Creating database PanaderiaDB...")
                cursor.execute("CREATE DATABASE PanaderiaDB")
            else:
                print("Database PanaderiaDB already exists.")
                
            conn.close()
            
            # Now connect to PanaderiaDB and run schema
            conn_db_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
            print(f"Connected to PanaderiaDB at {server}. Creating schema...")
            conn_db = pyodbc.connect(conn_db_str, autocommit=True)
            cursor_db = conn_db.cursor()
            
            with open('database/esquema.sql', 'r', encoding='utf-8') as f:
                sql_script = f.read()
            
            try:
                # Generar un hash real para la contraseña 'password123'
                default_hash = generate_password_hash('password123')

                # Split batches by GO
                batches = sql_script.split('\nGO')
                for batch in batches:
                    if batch.strip():
                        if 'hashed_pwd_aqui' in batch:
                            batch = batch.replace('hashed_pwd_aqui', default_hash)
                        cursor_db.execute(batch)
                print("Schema updated successfully!")
            except Exception as e:
                print("Error executing schema:", e)
                
            conn_db.close()
            print(f"SUCCESS: Set Config.SQL_SERVER_CONNECTION_STRING to: {conn_db_str}")
            return conn_db_str
            
        except Exception as e:
            print(f"Failed to connect to {server}: {e}")
            
    return None

if __name__ == '__main__':
    try_connect_and_setup()
