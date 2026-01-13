FROM ghcr.io/dimitri/pgloader:latest

# Instalar curl para las notificaciones HTTP y bash para el script
USER root
RUN apt-get update && apt-get install -y curl bash && rm -rf /var/lib/apt/lists/*

# Crear directorios de trabajo
WORKDIR /app

# Copiar el script de ejecución y darle permisos
COPY scripts/run_migration.sh /app/run_migration.sh
RUN chmod +x /app/run_migration.sh

# Volvemos a usuario no privilegiado si es necesario, 
# aunque pgloader a veces requiere root para ciertas operaciones de FS.
# Por compatibilidad con la imagen base, nos mantenemos o ajustamos según necesites.