import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pyodbc
from config import Config

conn = pyodbc.connect(Config.SQL_SERVER_CONNECTION_STRING)
cursor = conn.cursor()

# Create ConfiguracionSistema table
cursor.execute("""
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ConfiguracionSistema')
    CREATE TABLE ConfiguracionSistema (
        Clave VARCHAR(50) PRIMARY KEY NOT NULL,
        Valor VARCHAR(255) NOT NULL,
        Descripcion VARCHAR(200) NULL
    )
""")
conn.commit()

# Insert default values
defaults = [
    ('nombre_negocio', 'Panadería Amada', 'Nombre del negocio'),
    ('telefono_negocio', '', 'Teléfono de contacto'),
    ('direccion_negocio', '', 'Dirección física del negocio'),
    ('iva_porcentaje', '15', 'Porcentaje de IVA aplicado'),
    ('moneda_simbolo', 'C$', 'Símbolo de moneda'),
    ('totp_obligatorio', '0', 'Verificación en dos pasos obligatoria para empleados'),
    ('permitir_invitados', '1', 'Permitir acceso como cliente invitado'),
    ('max_items_factura', '50', 'Máximo de líneas por factura'),
]

for clave, valor, desc in defaults:
    cursor.execute("IF NOT EXISTS (SELECT 1 FROM ConfiguracionSistema WHERE Clave = ?) INSERT INTO ConfiguracionSistema VALUES (?, ?, ?)", clave, clave, valor, desc)

conn.commit()
conn.close()
print("ConfiguracionSistema table created and populated successfully.")
