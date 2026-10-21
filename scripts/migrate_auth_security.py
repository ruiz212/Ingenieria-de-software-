"""Idempotent authentication-state migration. No implicit .env/config loading.

Run only against an explicitly chosen database:
  python scripts/migrate_auth_security.py --connection-string ... --database ...
"""
import argparse
import os
import pyodbc

DDL = """
IF OBJECT_ID('seguridad.AuthChallenges', 'U') IS NULL
   AND OBJECT_ID('dbo.AuthChallenges', 'U') IS NULL
   AND OBJECT_ID('dbo.AuthChallenges', 'SN') IS NULL
BEGIN
    IF EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'seguridad')
    BEGIN
        CREATE TABLE [seguridad].[AuthChallenges] (
            Token VARCHAR(64) NOT NULL PRIMARY KEY,
            Kind VARCHAR(20) NOT NULL,
            Subject VARCHAR(32) NOT NULL,
            Verifier VARCHAR(64) NOT NULL DEFAULT '',
            Secret VARCHAR(64) NOT NULL DEFAULT '',
            Binding VARCHAR(64) NOT NULL DEFAULT '',
            ExpiresAt BIGINT NOT NULL,
            Attempts INT NOT NULL DEFAULT 0,
            Verified BIT NOT NULL DEFAULT 0,
            Consumed BIT NOT NULL DEFAULT 0,
            CONSTRAINT CK_AuthChallenges_Kind CHECK (Kind IN ('sms', 'totp_enroll', 'totp_login')),
            CONSTRAINT CK_AuthChallenges_Attempts CHECK (Attempts >= 0)
        );
        IF OBJECT_ID('dbo.AuthChallenges', 'SN') IS NULL
            EXEC('CREATE SYNONYM [dbo].[AuthChallenges] FOR [seguridad].[AuthChallenges]');
    END
    ELSE
    BEGIN
        CREATE TABLE dbo.AuthChallenges (
            Token VARCHAR(64) NOT NULL PRIMARY KEY,
            Kind VARCHAR(20) NOT NULL,
            Subject VARCHAR(32) NOT NULL,
            Verifier VARCHAR(64) NOT NULL DEFAULT '',
            Secret VARCHAR(64) NOT NULL DEFAULT '',
            Binding VARCHAR(64) NOT NULL DEFAULT '',
            ExpiresAt BIGINT NOT NULL,
            Attempts INT NOT NULL DEFAULT 0,
            Verified BIT NOT NULL DEFAULT 0,
            Consumed BIT NOT NULL DEFAULT 0,
            CONSTRAINT CK_AuthChallenges_Kind CHECK (Kind IN ('sms', 'totp_enroll', 'totp_login')),
            CONSTRAINT CK_AuthChallenges_Attempts CHECK (Attempts >= 0)
        );
    END
END;
IF OBJECT_ID('seguridad.AuthChallenges', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuthChallenges_Subject_Kind'
                   AND object_id = OBJECT_ID('seguridad.AuthChallenges', 'U'))
        CREATE INDEX IX_AuthChallenges_Subject_Kind ON [seguridad].[AuthChallenges] (Subject, Kind);
END
ELSE IF OBJECT_ID('dbo.AuthChallenges', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AuthChallenges_Subject_Kind'
                   AND object_id = OBJECT_ID('dbo.AuthChallenges', 'U'))
        CREATE INDEX IX_AuthChallenges_Subject_Kind ON dbo.AuthChallenges (Subject, Kind);
END;
"""


def migrate(connection_string, expected_database):
    if not connection_string or not expected_database:
        raise ValueError('Explicit connection string and database are required')
    conn = pyodbc.connect(connection_string)
    try:
        actual = conn.cursor().execute('SELECT DB_NAME()').fetchone()[0]
        if actual != expected_database:
            raise ValueError('Selected database does not match --database; migration aborted')
        conn.cursor().execute(DDL)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    connection = parser.add_mutually_exclusive_group(required=True)
    connection.add_argument('--connection-string')
    connection.add_argument('--connection-env', help='Nombre de variable de conexión; evita secretos en la línea de comandos.')
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    value = os.environ.get(args.connection_env) if args.connection_env else args.connection_string
    if not value:
        parser.error('La conexión indicada está vacía.')
    migrate(value, args.database)
