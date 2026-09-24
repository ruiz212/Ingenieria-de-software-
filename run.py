# run.py
# Punto de entrada del servidor Flask

from dotenv import load_dotenv
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Usar '::' (IPv6 dual-stack) en lugar de '0.0.0.0' soluciona el lag de 2 segundos 
    # al acceder vía 'localhost' en navegadores de Windows.
    app.run(debug=True, host='::', port=5000)
