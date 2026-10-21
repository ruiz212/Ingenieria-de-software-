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


def _resolve_table(cursor, name, default_schema='dbo'):
    row = cursor.execute(
        "SELECT TOP 1 s.name + '.' + t.name FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE t.name = ?",
        name
    ).fetchone()
    if row:
        return row[0]
    has_schema = cursor.execute("SELECT 1 FROM sys.schemas WHERE name = ?", default_schema).fetchone()
    return f"{default_schema}.{name}" if has_schema else f"dbo.{name}"


def migrate(connection):
    cursor = connection.cursor()
    for table, schema, column in [
        ('Facturas', 'ventas', 'DocumentoJSON'),
        ('ComprasMateriaPrima', 'produccion', 'IVADocumentado'),
        ('AsientosDiario', 'contabilidad', 'NumeroComprobante'),
        ('BitacoraFiscal', 'fiscal', 'Detalle'),
    ]:
        resolved = _resolve_table(cursor, table, schema)
        if cursor.execute('SELECT COL_LENGTH(?, ?)', resolved, column).fetchone()[0] is None:
            raise ValueError('Falta la migración fiscal/contable previa. No se alteró la fuente.')
    dgi_schema = 'fiscal' if cursor.execute("SELECT 1 FROM sys.schemas WHERE name='fiscal'").fetchone() else 'dbo'
    users_table = _resolve_table(cursor, 'Usuarios', 'seguridad')
    periodos_tbl = _resolve_table(cursor, 'DGI_Periodos', dgi_schema)
    revisiones_tbl = _resolve_table(cursor, 'DGI_Revisiones', dgi_schema)
    obs_tbl = _resolve_table(cursor, 'DGI_Observaciones', dgi_schema)
    exp_tbl = _resolve_table(cursor, 'DGI_Exportaciones', dgi_schema)
    cursor.execute(f"""
        IF OBJECT_ID('{periodos_tbl}', 'U') IS NULL
        CREATE TABLE {periodos_tbl} (
          ID INT IDENTITY PRIMARY KEY, Desde DATE NOT NULL, Hasta DATE NOT NULL,
          Estado VARCHAR(12) NOT NULL DEFAULT 'Abierto',
          CreadoPor INT NOT NULL REFERENCES {users_table}(ID),
          CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
          CONSTRAINT CK_DGI_PeriodoFechas CHECK (Hasta >= Desde),
          CONSTRAINT CK_DGI_PeriodoEstado CHECK (Estado IN ('Abierto','Cerrado')),
          CONSTRAINT UX_DGI_Periodo UNIQUE(Desde,Hasta));
    """)
    cursor.execute(f"""
        IF OBJECT_ID('{revisiones_tbl}', 'U') IS NULL
        CREATE TABLE {revisiones_tbl} (
          ID INT IDENTITY PRIMARY KEY, PeriodoID INT NOT NULL REFERENCES {periodos_tbl}(ID),
          Obligacion NVARCHAR(200) NOT NULL, Version INT NOT NULL,
          Motor VARCHAR(30) NOT NULL, Huella CHAR(64) NOT NULL,
          SnapshotJSON NVARCHAR(MAX) NOT NULL, ResultadoJSON NVARCHAR(MAX) NOT NULL,
          Estado VARCHAR(15) NOT NULL DEFAULT 'BORRADOR',
          CreadoPor INT NOT NULL REFERENCES {users_table}(ID),
          CreadoEn DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
          RevisadoPor INT NULL REFERENCES {users_table}(ID), RevisadoEn DATETIME2 NULL,
          NotaRevision NVARCHAR(1000) NULL,
          AprobadoPor INT NULL REFERENCES {users_table}(ID), AprobadoEn DATETIME2 NULL,
          CONSTRAINT CK_DGI_RevisionEstado CHECK
            (Estado IN ('BORRADOR','EN_REVISION','APROBADO','EXPORTADO','OBSOLETO')),
          CONSTRAINT UX_DGI_Revision UNIQUE(PeriodoID,Obligacion,Version));
    """)
    cursor.execute(f"""
        IF OBJECT_ID('{obs_tbl}', 'U') IS NULL
        CREATE TABLE {obs_tbl} (
          ID INT IDENTITY PRIMARY KEY,
          RevisionID INT NOT NULL REFERENCES {revisiones_tbl}(ID),
          Hallazgo CHAR(24) NOT NULL, Comentario NVARCHAR(1000) NOT NULL,
          UsuarioID INT NOT NULL REFERENCES {users_table}(ID),
          Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
    """)
    cursor.execute(f"""
        IF OBJECT_ID('{exp_tbl}', 'U') IS NULL
        CREATE TABLE {exp_tbl} (
          ID INT IDENTITY PRIMARY KEY,
          RevisionID INT NOT NULL REFERENCES {revisiones_tbl}(ID),
          Nombre NVARCHAR(150) NOT NULL, SHA256 CHAR(64) NOT NULL,
          Archivo VARBINARY(MAX) NOT NULL,
          UsuarioID INT NOT NULL REFERENCES {users_table}(ID),
          Fecha DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
    """)
    for key, value in DEFAULTS.items():
        cursor.execute("""IF NOT EXISTS(SELECT 1 FROM ConfiguracionSistema WHERE Clave=?)
            INSERT INTO ConfiguracionSistema(Clave,Valor,Descripcion) VALUES(?,?,?)""",
                       key, key, value, 'Preparación interna DGI; no valida inscripción ni normativa')


def downgrade(connection):
    """Solo desinstala una instalación vacía, dentro de una transacción."""
    cursor = connection.cursor()
    cursor.execute("EXEC sys.sp_set_session_context @key=N'allow_ddl_migration', @value=1;")
    cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
    for table in TABLES:
        resolved = _resolve_table(cursor, table, 'fiscal')
        if cursor.execute('SELECT OBJECT_ID(?, ?)', resolved, 'U').fetchone()[0]:
            if cursor.execute(f'SELECT TOP 1 ID FROM {resolved} WITH (TABLOCKX,HOLDLOCK)').fetchone():
                raise ValueError('Reversión denegada: hay datos DGI. Conserve el historial.')
    for key, value in DEFAULTS.items():
        row = cursor.execute('SELECT Valor FROM ConfiguracionSistema WITH (UPDLOCK,HOLDLOCK) WHERE Clave=?', key).fetchone()
        if row and row[0] != value:
            raise ValueError('Reversión denegada: existe un perfil DGI configurado.')
    for table in TABLES:
        resolved = _resolve_table(cursor, table, 'fiscal')
        cursor.execute(f"IF OBJECT_ID('{resolved}', 'U') IS NOT NULL DROP TABLE {resolved}")
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
