FROM python:3.12-slim-bookworm

# Evitar prompts interactivos durante apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema para pyodbc y OpenCV
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc-dev \
    build-essential \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Instalar Microsoft ODBC Driver 18 for SQL Server
RUN curl -fsSLo /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/* /tmp/packages-microsoft-prod.deb

# Configurar el directorio de trabajo
WORKDIR /app

# Copiar el archivo de requerimientos e instalarlos
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && pip check

# Copiar el resto del código
COPY . .

# Fail the build if the selected context accidentally includes local credentials.
RUN test ! -e /app/.env && test ! -e /app/scratch && test ! -e /app/.git

# Exponer el puerto
EXPOSE 8000

# Comando de inicio
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--timeout", "600", "run:app"]
