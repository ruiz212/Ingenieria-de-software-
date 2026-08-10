import pyodbc
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def test_connection():
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    print("Testing connection string:", conn_str)
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print("Connected successfully!")
        print("SQL Server version:", row[0])
        conn.close()
    except Exception as e:
        print("Error connecting to database:")
        print(e)

if __name__ == '__main__':
    test_connection()
