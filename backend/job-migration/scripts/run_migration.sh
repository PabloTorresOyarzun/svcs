#!/bin/bash

# Configuración inicial
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# ---------------------------------------------------------------------------
# FIX DE CONEXIONES (CORREGIDO: Ahora sí exportamos las variables)
# ---------------------------------------------------------------------------
mkdir -p /etc/freetds
cat <<EOF > /etc/freetds/freetds.conf
[global]
    tds version = 7.4
    client charset = UTF-8
    connect timeout = 60
    timeout = 60
    text size = 64512
    max connections = 4096
EOF

# ESTAS SON LAS LÍNEAS QUE FALTABAN PARA QUE LEA LA CONFIGURACIÓN
export FREETDSCONF=/etc/freetds/freetds.conf
export TDS_MAX_CONN=4096
# ---------------------------------------------------------------------------

# Definimos las reglas de conversión comunes
CAST_RULES="
CAST
    type tinyint to smallint drop default drop not null,
    type numeric drop default drop not null,
    type decimal drop default drop not null,
    type money to numeric drop default drop not null,
    type smallmoney to numeric drop default drop not null,
    type int drop default drop not null,
    type smallint drop default drop not null,
    type bigint drop default drop not null,
    type float to float8 drop typemod drop default using (lambda (n) (if n (format nil \"~f\" n) nil)),
    type real to float4 drop typemod drop default using (lambda (n) (if n (format nil \"~f\" n) nil)),
    type datetime to timestamptz drop default drop not null using zero-dates-to-null,
    type datetime2 to timestamptz drop default drop not null using zero-dates-to-null,
    type smalldatetime to timestamptz drop default drop not null using zero-dates-to-null,
    type date to date drop default drop not null using zero-dates-to-null,
    type image to bytea,
    type bit to boolean,
    type char to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type nchar to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type varchar to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type nvarchar to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type xml to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type text to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil)),
    type ntext to text drop default drop typemod using (lambda (s) (if s (remove (code-char 0) s) nil));
"

# Función maestra
run_migration_step() {
    DB_NAME=$1
    EXTRA_CONFIG=$2 

    echo "----------------------------------------------------------------"
    echo ">>> MIGRANDO BASE DE DATOS: $DB_NAME"
    echo "----------------------------------------------------------------"

    # Generar archivo temporal
    # FIX: Bajamos prefetch rows a 1 para máxima estabilidad
    cat <<EOF > /tmp/current_migration.load
LOAD DATABASE
    FROM $MSSQL_BASE_URL/$DB_NAME
    INTO $PG_TARGET_URL

WITH include drop, create tables, create indexes, reset sequences, foreign keys,
     workers = 1, concurrency = 1, batch rows = 50, prefetch rows = 1

SET PostgreSQL PARAMETERS
    statement_timeout = '0', lock_timeout = '0', work_mem = '64MB',
    maintenance_work_mem = '256MB', standard_conforming_strings = 'on'

ALTER SCHEMA 'dbo' RENAME TO '$DB_NAME'

EXCLUDING TABLE NAMES LIKE 'dtproperties' IN SCHEMA 'dbo'

$CAST_RULES

$EXTRA_CONFIG
EOF

    # Ejecutar pgloader
    pgloader --verbose --dynamic-space-size 4096 /tmp/current_migration.load
}

echo "[$TIMESTAMP] INICIO MIGRACIÓN SECUENCIAL (INTENTO DEFINITIVO)"

# 1. VIN
run_migration_step "vin" ""

# 2. EXPORTACION
run_migration_step "exportacion" ""

# 3. EXPORTASIS
run_migration_step "exportasis" ""

# 4. SISCON
SISCON_FIX="
AFTER LOAD DO
\$\$
DO \$fix_siscon\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_enviosmail_tipodte' AND conrelid = 'siscon.enviosmail'::regclass) THEN
        ALTER TABLE siscon.enviosmail ADD CONSTRAINT uk_enviosmail_tipodte UNIQUE (tipodte);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_enviosmail_foliodte' AND conrelid = 'siscon.enviosmail'::regclass) THEN
        ALTER TABLE siscon.enviosmail ADD CONSTRAINT uk_enviosmail_foliodte UNIQUE (foliodte);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_enviosmail_tipodte' AND conrelid = 'siscon.enviosmail'::regclass) THEN
        ALTER TABLE siscon.enviosmail ADD CONSTRAINT fk_enviosmail_tipodte FOREIGN KEY (tipodte) REFERENCES siscon.enviosmail(tipodte) ON UPDATE NO ACTION ON DELETE NO ACTION;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_enviosmail_foliodte' AND conrelid = 'siscon.enviosmail'::regclass) THEN
        ALTER TABLE siscon.enviosmail ADD CONSTRAINT fk_enviosmail_foliodte FOREIGN KEY (foliodte) REFERENCES siscon.enviosmail(foliodte) ON UPDATE NO ACTION ON DELETE NO ACTION;
    END IF;
    RAISE NOTICE '✓ Correcciones de siscon completadas';
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Error al corregir siscon: %', SQLERRM;
END \$fix_siscon\$;
\$\$;
"
run_migration_step "siscon" "$SISCON_FIX"

# 5. BD_FACTURA
run_migration_step "BD_FACTURA" ""

# 6. DECLARACION
run_migration_step "declaracion" ""

echo "[$TIMESTAMP] ✅ PROCESO COMPLETO."