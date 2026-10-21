"""Fail-closed connection boundary for tests; never used for normal requests."""
import re


def require_qa_string(connection_string):
    # Reject duplicate database keys rather than guessing which one ODBC uses.
    values=re.findall(r'(?:^|;)\s*(?:DATABASE|INITIAL CATALOG)\s*=\s*(\{[^}]*\}|[^;]*)',str(connection_string),re.I)
    if len(values)!=1 or not values[0].strip().strip('{}').lower().startswith('panaderiaqa_'):
        raise ValueError('Pruebas SQL: configure exclusivamente una base PanaderiaQA_.')
    return connection_string


_VERIFY_DB_SQL = 'SELECT DB_NAME()'


def connect_qa(connect, connection_string, *args, **kwargs):
    require_qa_string(connection_string)
    # An autocommit connection could run unintended writes before verification.
    if kwargs.get('database') or kwargs.get('dsn'):
        raise ValueError('Pruebas SQL: la base QA debe definirse en la cadena única.')
    connection=connect(connection_string,*args,**kwargs)
    try:
        row=connection.cursor().execute(_VERIFY_DB_SQL).fetchone()
        if not row or not str(row[0]).lower().startswith('panaderiaqa_'):
            raise ValueError('Pruebas SQL: el servidor devolvió una base distinta de QA.')
    except BaseException:
        connection.close()
        raise
    return connection
