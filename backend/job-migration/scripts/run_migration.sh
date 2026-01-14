#!/bin/bash

# Configuración
# NOTIFY_API_URL="http://sgd-api:8001/api/internal/notifications" # Descomentar cuando exista
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_TIME=$(date +%s)

echo "[$TIMESTAMP] Iniciando proceso de migración (MODO ROBUSTO - 4GB RAM)..."

# 1. Preparar archivo de configuración (Reemplazo de variables)
# Se usa 'sed' para inyectar las variables de entorno en la plantilla
if ! sed -e 's|__MSSQL_BASE_URL__|'"$MSSQL_BASE_URL"'|g' \
         -e 's|__PG_TARGET_URL__|'"$PG_TARGET_URL"'|g' \
         /migration.template > /migration.load; then
    echo "ERROR: Falló la creación del archivo de configuración."
    exit 1
fi

# 2. Ejecutar Pgloader y capturar salida
# CAMBIO CRÍTICO: --dynamic-space-size 4096 asigna 4GB de RAM al heap de Lisp.
# Esto evita el error "LPARALLEL" y "Heap exhaustion".
OUTPUT=$(pgloader --verbose --dynamic-space-size 4096 /migration.load 2>&1)
EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# 3. Analizar Resultado
if [ $EXIT_CODE -eq 0 ]; then
    STATUS="success"
    MESSAGE="Migración completada exitosamente en ${DURATION} segundos."
    echo "[$TIMESTAMP] ÉXITO: $MESSAGE"
else
    STATUS="error"
    MESSAGE="Fallo crítico en la migración (Código: $EXIT_CODE)."
    echo "[$TIMESTAMP] ERROR: $MESSAGE"
    # Imprimir las últimas líneas del log para depuración inmediata en consola
    echo "--- ÚLTIMAS LÍNEAS DEL LOG ---"
    echo "$OUTPUT" | tail -n 40
    echo "------------------------------"
fi

# 4. Notificación (PREPARADA PARA EL FUTURO)
# Cuando tengas tu API lista, solo descomenta el bloque siguiente:

# JSON_PAYLOAD=$(cat <<EOF
# {
#   "source": "job-migration",
#   "event": "db_sync",
#   "status": "$STATUS",
#   "timestamp": "$TIMESTAMP",
#   "message": "$MESSAGE",
#   "details": {
#       "duration_seconds": $DURATION,
#       "exit_code": $EXIT_CODE,
#       "log_snippet": "$(echo "$OUTPUT" | tail -n 10 | sed 's/"/\\"/g')" 
#   }
# }
# EOF
# )

# curl -X POST "$NOTIFY_API_URL" \
#      -H "Content-Type: application/json" \
#      -H "Authorization: Bearer $ADMIN_TOKEN" \
#      -d "$JSON_PAYLOAD" || echo "Advertencia: No se pudo enviar la notificación"

exit $EXIT_CODE