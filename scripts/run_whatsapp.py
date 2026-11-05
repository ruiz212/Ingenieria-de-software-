"""Run separately from Flask/Gunicorn or via managed supervisor: python scripts/run_whatsapp.py."""
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['_WHATSAPP_WORKER_PROCESS'] = '1'
from dotenv import load_dotenv
load_dotenv()
from app import create_app
from app.whatsapp.worker import run


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    app = create_app()
    while True:
        try:
            run(app)
        except ValueError as exc:
            logging.getLogger('whatsapp.supervisor').warning('Worker WhatsApp en pausa: %s', exc)
            time.sleep(15)
        except RuntimeError as exc:
            if 'Ya existe un worker WhatsApp activo' in str(exc):
                time.sleep(10)
            else:
                logging.getLogger('whatsapp.supervisor').info('Reconectando sesión WhatsApp (%s)...', exc)
                time.sleep(2)
        except Exception:
            logging.getLogger('whatsapp.supervisor').exception('Error en worker WhatsApp; reintentando en 4s...')
            time.sleep(4)


if __name__ == '__main__':
    main()
