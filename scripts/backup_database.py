"""Respaldo SQL Server a ruta del servidor. No sobrescribe archivos ni restaura datos.

Uso: python scripts/backup_database.py --connection-env DB_CONNECTION_STRING --directory D:\\Respaldos
Azure SQL Database requiere respaldos administrados/PITR; este comando no los sustituye.
"""
import argparse
import os
import ntpath
import uuid
from datetime import datetime
import pyodbc


def backup(connection_string, directory):
    if not ntpath.isabs(directory):
        raise ValueError('La carpeta debe ser absoluta y accesible por el servicio SQL Server.')
    connection = pyodbc.connect(connection_string, autocommit=True)
    try:
        cursor = connection.cursor()
        name, edition = cursor.execute("SELECT DB_NAME(), CONVERT(INT,SERVERPROPERTY('EngineEdition'))").fetchone()
        if edition == 5:
            raise ValueError('Azure SQL Database: use el respaldo administrado y compruebe una restauración PITR en otra base.')
        safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
        filename = f'{safe_name}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.bak'
        destination = ntpath.join(directory, filename)
        quoted_name = '[' + name.replace(']', ']]') + ']'
        cursor.execute(f'BACKUP DATABASE {quoted_name} TO DISK=? WITH COPY_ONLY, CHECKSUM', destination)
        while cursor.nextset():
            pass
        cursor.execute('RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM', destination)
        while cursor.nextset():
            pass
        return destination
    finally:
        connection.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--directory', required=True)
    args=parser.parse_args()
    print('Respaldo verificado:',backup(os.environ[args.connection_env],args.directory))
