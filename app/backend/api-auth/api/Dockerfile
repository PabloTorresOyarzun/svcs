FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Santiago

# Usuario no-root (OWASP)
RUN useradd --create-home --shell /bin/bash appuser

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo fuente
COPY src/ ./src/

# Permisos
RUN chown -R appuser:appuser /app
USER appuser

ENV LITESTAR_APP=src.app:app

EXPOSE 8000

CMD ["litestar", "run", "--host", "0.0.0.0", "--port", "8000"]