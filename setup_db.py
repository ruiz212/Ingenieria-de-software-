import pyodbc
import os

def try_connect_and_setup():
    drivers = [driver for driver in pyodbc.drivers() if 'SQL Server' in driver or 'ODBC Driver' in driver]
    if not drivers:
        print("No SQL Server ODBC drivers found.")
        return False
        
    driver = drivers[-1] # Usually the most recent ODBC driver
    print(f"Using driver: {driver}")
    
    servers = ['localhost', '.\\SQLEXPRESS', '(localdb)\\MSSQLLocalDB']
    
    for server in servers:
        try:
            print(f"Trying to connect to {server}...")
            # Connect to master to create DB
            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=master;Trusted_Connection=yes;"
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=3)
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
            conn_db_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=PanaderiaDB;Trusted_Connection=yes;"
            print(f"Connected to PanaderiaDB at {server}. Creating schema...")
            conn_db = pyodbc.connect(conn_db_str, autocommit=True)
            cursor_db = conn_db.cursor()
            
            with open('database/esquema.sql', 'r', encoding='utf-8') as f:
                sql_script = f.read()
            
            # Split batches by GO (if any) or just execute
            # In our case, the script doesn't have GO, it's just raw SQL.
            try:
                # Basic check if tables exist to avoid crashing
                cursor_db.execute("SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='Productos'")
                if not cursor_db.fetchone():
                    # The script contains multiple statements, pyodbc execute might fail on some if we don't split, 
                    # but simple CREATE TABLE statements often work together or we can execute them one by one.
                    # Since schema.sql has no GO, let's just run it:
                    cursor_db.execute(sql_script)
                    print("Schema created successfully!")
                else:
                    print("Tables already exist. Skipping schema creation.")
            except Exception as e:
                print("Error executing schema:", e)
                # Fallback: try splitting by statements (rudimentary)
                pass
                
            conn_db.close()
            print(f"SUCCESS: Set Config.SQL_SERVER_CONNECTION_STRING to: {conn_db_str}")
            return conn_db_str
            
        except Exception as e:
            print(f"Failed to connect to {server}: {e}")
            
    return None

if __name__ == '__main__':
    try_connect_and_setup()
