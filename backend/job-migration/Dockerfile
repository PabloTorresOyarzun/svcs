FROM python:3.12-slim-bookworm

# 1. Configurar OpenSSL para permitir conexiones a SQL Server antiguos
# Esto es vital en Debian 12 (Bookworm)
RUN sed -i 's/CipherString = DEFAULT:@SECLEVEL=2/CipherString = DEFAULT:@SECLEVEL=1/g' /etc/ssl/openssl.cnf

# 2. Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    ca-certificates

# 3. Configurar repositorio de Microsoft CORRECTAMENTE para Debian 12
# Descargamos la llave y la convertimos/guardamos en el keyring oficial
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    # Descargamos la lista de repositorios
    && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    # IMPORTANTE: No basta con bajar el archivo, hay que decirle a APT dónde está la llave.
    # Editamos el archivo .list para agregar [signed-by=...] si no lo trae, o confiamos en que apt moderno lo detecte
    # En este caso, el repo de MS suele necesitar ayuda o usar la llave global.
    # El paso clave que fallaba antes era la importación de la llave.
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]