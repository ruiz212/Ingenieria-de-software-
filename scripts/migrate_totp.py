import os
import sys
import pyodbc

# Add parent directory to path so we can import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from config import Config

def migrate():
    print("Connecting to database...")
    try:
        conn = pyodbc.connect(Config.SQL_SERVER_CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'Usuarios' AND COLUMN_NAME = 'TOTPSecret'
        """)
        
        if not cursor.fetchone():
            print("Adding TOTPSecret column...")
            cursor.execute("ALTER TABLE Usuarios ADD TOTPSecret VARCHAR(32) NULL")
        else:
            print("TOTPSecret column already exists.")
            
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'Usuarios' AND COLUMN_NAME = 'TOTPEnabled'
        """)
        
        if not cursor.fetchone():
            print("Adding TOTPEnabled column...")
            cursor.execute("ALTER TABLE Usuarios ADD TOTPEnabled BIT NOT NULL DEFAULT 0")
        else:
            print("TOTPEnabled column already exists.")
            
        conn.commit()
        print("Migration completed successfully.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrate()
