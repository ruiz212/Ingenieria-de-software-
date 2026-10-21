"""Checked positive waste and exact cash exchange rates; no historical edits."""
import argparse
import os
import pyodbc


def migrate(connection, expected_database):
    if not expected_database:
        raise ValueError('Indique explícitamente la base de destino.')
    cursor=connection.cursor()
    if cursor.execute('SELECT DB_NAME()').fetchone()[0]!=expected_database:
        raise ValueError('La base seleccionada no coincide; migración cancelada.')
    invalid=cursor.execute('SELECT COUNT(*) FROM Mermas WHERE Cantidad IS NULL OR Cantidad <= 0').fetchone()[0]
    if invalid:
        raise ValueError(f'Hay {invalid} mermas históricas inválidas. Revise su origen antes de aplicar la restricción; no se cambió ningún registro.')
    cursor.execute("""IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
        WHERE name='CK_Mermas_CantidadPositiva' AND parent_object_id=OBJECT_ID('dbo.Mermas'))
        ALTER TABLE dbo.Mermas WITH CHECK ADD CONSTRAINT CK_Mermas_CantidadPositiva
        CHECK (Cantidad IS NOT NULL AND Cantidad > 0);
        ALTER TABLE dbo.Mermas WITH CHECK CHECK CONSTRAINT CK_Mermas_CantidadPositiva;""")
    cursor.execute('ALTER TABLE dbo.ArqueoCaja ALTER COLUMN TipoCambioUsado DECIMAL(12,6) NULL')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env',required=True)
    parser.add_argument('--database',required=True)
    args=parser.parse_args()
    value=os.environ.get(args.connection_env)
    if not value:parser.error('La variable de conexión indicada está vacía.')
    conn=pyodbc.connect(value)
    try:
        migrate(conn,args.database)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
