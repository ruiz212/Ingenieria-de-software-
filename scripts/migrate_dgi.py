"""Migración aditiva de preparación DGI. No modifica fuentes comerciales.

python scripts/migrate_dgi.py --connection-env TEST_DB_CONNECTION_STRING
Reversión de instalación vacía: agregar --down. Nunca elimina revisiones.
"""
import argparse
import os
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

DEFAULTS = {
    'dgi_obligaciones': '', 'dgi_responsable': '',
    'dgi_vigente_desde': '', 'dgi_vigente_hasta': '',
}
TABLES = ('DGI_Exportaciones', 'DGI_Observaciones', 'DGI_Revisiones', 'DGI_Periodos')


def migrate(connection):
    cursor = connection.cursor()
    for table, column in [('Facturas', 'DocumentoJSON'), ('ComprasMateriaPrima', 'IVADocumentado'),
                          ('AsientosDiario', 'NumeroComprobante'), ('BitacoraFiscal', 'Detalle')]:
        if cursor.execute('SELECT COL_LENGTH(?, ?)', table, column).fetchone()[0] is None:
            raise ValueError('Falta la migración fiscal/contable previa. No se alteró la fuente.')
    cursor.execute("""
        IF OBJECT_ID('DGI_Periodos', 'U') IS NULL
        CREATE TABLE DGI_Periodos (
          ID INT IDENTITY PRIMARY KEY, Desde DATE NOT NULL, Hasta DATE NOT NULL,
          Estado VARCHAR(12) NOT NULL DEFAULT 'Abierto',
          CreadoPor INT NOT NULL REFERENCES Usuarios(ID),
          CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
          CONSTRAINT CK_DGI_PeriodoFechas CHECK (Hasta >= Desde),
          CONSTRAINT CK_DGI_PeriodoEstado CHECK (Estado IN ('Abierto','Cerrado')),
          CONSTRAINT UX_DGI_Periodo UNIQUE(Desde,Hasta));
    """)
    cursor.execute("""
        IF OBJECT_ID('DGI_Revisiones', 'U') IS NULL
        CREATE TABLE DGI_Revisiones (
          ID INT IDENTITY PRIMARY KEY, PeriodoID INT NOT NULL REFERENCES DGI_Periodos(ID),
          Obligacion NVARCHAR(200) NOT NULL, Version INT NOT NULL,
          Motor VARCHAR(30) NOT NULL, Huella CHAR(64) NOT NULL,
          SnapshotJSON NVARCHAR(MAX) NOT NULL, ResultadoJSON NVARCHAR(MAX) NOT NULL,
          Estado VARCHAR(15) NOT NULL DEFAULT 'BORRADOR',
          CreadoPor INT NOT NULL REFERENCES Usuarios(ID),
          CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
          RevisadoPor INT NULL REFERENCES Usuarios(ID), RevisadoEn DATETIME2 NULL,
          NotaRevision NVARCHAR(1000) NULL,
          AprobadoPor INT NULL REFERENCES Usuarios(ID), AprobadoEn DATETIME2 NULL,
          CONSTRAINT CK_DGI_RevisionEstado CHECK
            (Estado IN ('BORRADOR','EN_REVISION','APROBADO','EXPORTADO','OBSOLETO')),
          CONSTRAINT UX_DGI_Revision UNIQUE(PeriodoID,Obligacion,Version));
    """)
    cursor.execute("""
        IF OBJECT_ID('DGI_Observaciones', 'U') IS NULL
        CREATE TABLE DGI_Observaciones (
          ID INT IDENTITY PRIMARY KEY,
          RevisionID INT NOT NULL REFERENCES DGI_Revisiones(ID),
          Hallazgo CHAR(24) NOT NULL, Comentario NVARCHAR(1000) NOT NULL,
          UsuarioID INT NOT NULL REFERENCES Usuarios(ID),
          Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
    """)
    cursor.execute("""
        IF OBJECT_ID('DGI_Exportaciones', 'U') IS NULL
        CREATE TABLE DGI_Exportaciones (
          ID INT IDENTITY PRIMARY KEY,
          RevisionID INT NOT NULL REFERENCES DGI_Revisiones(ID),
          Nombre NVARCHAR(150) NOT NULL, SHA256 CHAR(64) NOT NULL,
          Archivo VARBINARY(MAX) NOT NULL,
          UsuarioID INT NOT NULL REFERENCES Usuarios(ID),
          Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
    """)
    for key, value in DEFAULTS.items():
        cursor.execute("""IF NOT EXISTS(SELECT 1 FROM ConfiguracionSistema WHERE Clave=?)
            INSERT INTO ConfiguracionSistema(Clave,Valor,Descripcion) VALUES(?,?,?)""",
                       key, key, value, 'Preparación interna DGI; no valida inscripción ni normativa')


def downgrade(connection):
    """Solo desinstala una instalación vacía, dentro de una transacción."""
    cursor = connection.cursor()
    cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
    for table in TABLES:
        if cursor.execute('SELECT OBJECT_ID(?, ?)', table, 'U').fetchone()[0]:
            if cursor.execute(f'SELECT TOP 1 ID FROM {table} WITH (TABLOCKX,HOLDLOCK)').fetchone():
                raise ValueError('Reversión denegada: hay datos DGI. Conserve el historial.')
    for key, value in DEFAULTS.items():
        row = cursor.execute('SELECT Valor FROM ConfiguracionSistema WITH (UPDLOCK,HOLDLOCK) WHERE Clave=?', key).fetchone()
        if row and row[0] != value:
            raise ValueError('Reversión denegada: existe un perfil DGI configurado.')
    for table in TABLES:
        cursor.execute(f"IF OBJECT_ID('{table}', 'U') IS NOT NULL DROP TABLE {table}")
    for key in DEFAULTS:
        cursor.execute('DELETE FROM ConfiguracionSistema WHERE Clave=?', key)


if __name__ == '__main__':
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--down', action='store_true')
    args = parser.parse_args()
    with pyodbc.connect(os.environ[args.connection_env]) as connection:
        try:
            (downgrade if args.down else migrate)(connection)
            connection.commit()
            print('Migración DGI completada.' if not args.down else 'Instalación DGI vacía revertida.')
        except Exception:
            connection.rollback()
            raise
