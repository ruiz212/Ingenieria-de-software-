import sys
import os
from pathlib import Path
import pytest

# Agregar raíz del proyecto a sys.path
root_dir = str(Path(__file__).parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Tests must opt into a named QA database. Never load the application's .env.
os.environ['PYTHON_DOTENV_DISABLED']='1'
from app.qa_safety import connect_qa,require_qa_string
import pyodbc
from config import Config

_original_connect=pyodbc.connect
_qa_string=os.environ.get('TEST_DB_CONNECTION_STRING','')
if _qa_string:
    require_qa_string(_qa_string)
Config.SQL_SERVER_CONNECTION_STRING=_qa_string


def _guarded_connect(connection_string='',*args,**kwargs):
    return connect_qa(_original_connect,connection_string,*args,**kwargs)


pyodbc.connect=_guarded_connect


@pytest.fixture(autouse=True)
def restore_login_loader():
    # Flask-Login's extension is shared by factories; fixtures must not leak roles.
    from app.extensions import login_manager
    from app.models import load_user
    login_manager._user_callback=load_user
    yield
    login_manager._user_callback=load_user
