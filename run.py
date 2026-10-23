# run.py
# Punto de entrada del servidor Flask

from dotenv import load_dotenv
import os
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Usar '::' (IPv6 dual-stack) en lugar de '0.0.0.0' soluciona el lag de 2 segundos 
    # al acceder vía 'localhost' en navegadores de Windows.
    # reloader_type='stat' evita reinicios espurios de watchdog en librerías estándar en Windows (Python 3.14)
    app.run(
        debug=os.getenv('FLASK_DEBUG', '1') == '1',
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', '5000')),
        reloader_type='stat'
    )
