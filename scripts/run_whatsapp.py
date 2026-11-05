"""Run separately from Flask/Gunicorn: python scripts/run_whatsapp.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()
from app import create_app
from app.whatsapp.worker import run

if __name__ == '__main__':
    run(create_app())
