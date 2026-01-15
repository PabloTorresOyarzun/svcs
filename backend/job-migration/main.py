import sys
import os
import time
import logging
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool  # Vital para limpiar la conexión MSSQL
from urllib.parse import quote_plus
from sqlalchemy.types import Integer, Text, String, DateTime, Boolean, Numeric, BigInteger, Float, Date, Time, LargeBinary, SmallInteger
from sqlalchemy.dialects import mssql, postgresql

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Variables de Entorno ---
MSSQL_USER = os.getenv('MSSQL_USER')
MSSQL_PASS = os.getenv('MSSQL_PASS')
MSSQL_HOST = os.getenv('MSSQL_HOST')
MSSQL_PORT = os.getenv('MSSQL_PORT', '1433')
SOURCE_DBS = ["vin", "exportacion", "exportasis", "siscon", "BD_FACTURA", "declaracion"]

PG_USER = os.getenv('PG_USER')
PG_PASS = os.getenv('PG_PASS')
PG_HOST = os.getenv('PG_HOST')
PG_PORT = os.getenv('PG_PORT', '5432')
PG_DB =   os.getenv('PG_DB')

# --- Configuración de Resiliencia ---
INITIAL_CHUNK_SIZE = 10000
MIN_CHUNK_SIZE = 100      # Muy bajo para aislar errores graves
MAX_RETRIES = 10          # Insistimos mucho
DB_MAX_RETRIES = 5        # Intentos de conexión global a la DB

# Almacén global de FKs para aplicar al final
PENDING_FKS = {}

if not all([MSSQL_USER, MSSQL_PASS, MSSQL_HOST, PG_USER, PG_PASS, PG_HOST, PG_DB]):
    logger.error("Faltan variables de entorno. Abortando.")
    sys.exit(1)

def get_mssql_engine(db_name):
    params = quote_plus(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={MSSQL_HOST},{MSSQL_PORT};"
        f"DATABASE={db_name};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASS};"
        "TrustServerCertificate=yes;"
    )
    # NullPool: Crea una conexión TCP nueva para cada operación.
    # Soluciona el error 0x2746 y limpia el estado SSL del driver.
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}", 
        fast_executemany=True,
        poolclass=NullPool
    )

def get_pg_engine():
    return create_engine(
        f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}",
        pool_pre_ping=True
    )

def get_precise_type(mssql_type):
    """Mapeo robusto de tipos."""
    try:
        # Fix para tipo 'sysname'
        if str(mssql_type).lower() == 'sysname':
            return String(128)
            
        if isinstance(mssql_type, (mssql.DECIMAL, mssql.NUMERIC)):
            p = getattr(mssql_type, 'precision', None)
            s = getattr(mssql_type, 'scale', None)
            return Numeric(precision=p, scale=s) if p else Numeric()
        if isinstance(mssql_type, mssql.BIT): return Boolean()
        if isinstance(mssql_type, mssql.TINYINT): return SmallInteger()
        if isinstance(mssql_type, (mssql.SMALLINT, mssql.INTEGER)): return Integer()
        if isinstance(mssql_type, mssql.BIGINT): return BigInteger()
        if isinstance(mssql_type, (mssql.VARCHAR, mssql.NVARCHAR, mssql.CHAR, mssql.NCHAR)):
            l = getattr(mssql_type, 'length', None)
            return String(length=l) if (l and l < 10485760) else Text()
        if isinstance(mssql_type, (mssql.DATETIME, mssql.DATETIME2, mssql.SMALLDATETIME)): return DateTime()
        if isinstance(mssql_type, mssql.DATE): return Date()
        if isinstance(mssql_type, mssql.TIME): return Time()
        if isinstance(mssql_type, (mssql.VARBINARY, mssql.BINARY, mssql.IMAGE)): return LargeBinary()
        if isinstance(mssql_type, mssql.UNIQUEIDENTIFIER): return postgresql.UUID(as_uuid=True)
        if isinstance(mssql_type, (mssql.MONEY, mssql.SMALLMONEY)): return Numeric(precision=19, scale=4)
    except Exception:
        pass
    return Text()

def clean_dataframe(df, dtype_mapping):
    """Limpieza de datos."""
    for col_name, sql_type in dtype_mapping.items():
        if col_name not in df.columns: continue
        if isinstance(sql_type, (DateTime, Date)):
            df[col_name] = pd.to_datetime(df[col_name], errors='coerce')
        if isinstance(sql_type, postgresql.UUID):
            df[col_name] = df[col_name].astype(str)
        if isinstance(sql_type, (String, Text)):
             df[col_name] = df[col_name].astype(str).str.replace('\x00', '', regex=False)
             df[col_name] = df[col_name].replace({'None': None, 'nan': None})
    return df

def get_pk_columns_raw(mssql_engine, table_name):
    """Obtiene PKs reales consultando sys.indexes."""
    sql = text(f"""
        SELECT c.name
        FROM sys.indexes i
        INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND c.column_id = ic.column_id
        INNER JOIN sys.objects o ON i.object_id = o.object_id
        WHERE i.is_primary_key = 1
        AND o.name = :tname
        ORDER BY ic.key_ordinal;
    """)
    try:
        with mssql_engine.connect() as conn:
            result = conn.execute(sql, {"tname": table_name}).fetchall()
            return [row[0] for row in result]
    except Exception as e:
        logger.warning(f"Error consultando PK para {table_name}: {e}")
        return []

def harvest_foreign_keys(mssql_engine, db_name, table_name):
    """Guarda las FKs para crearlas al final."""
    try:
        inspector = inspect(mssql_engine)
        fks = inspector.get_foreign_keys(table_name)
        
        if db_name not in PENDING_FKS:
            PENDING_FKS[db_name] = []

        for fk in fks:
            fk_name = fk['name'] or f"fk_{table_name}_{fk['referred_table']}"
            fk_name = fk_name.replace(" ", "_").replace(".", "_")[:60]
            cols = '", "'.join(fk['constrained_columns'])
            ref_table = fk['referred_table']
            ref_cols = '", "'.join(fk['referred_columns'])

            sql = f"""
                ALTER TABLE "{db_name}"."{table_name}"
                ADD CONSTRAINT "{fk_name}" 
                FOREIGN KEY ("{cols}") 
                REFERENCES "{db_name}"."{ref_table}" ("{ref_cols}")
                ON DELETE NO ACTION;
            """
            PENDING_FKS[db_name].append({
                'table': table_name,
                'sql': sql,
                'desc': f"{table_name}->{ref_table}"
            })
    except Exception:
        pass

def restore_primary_key(pg_engine, db_name, table_name, pk_columns):
    if not pk_columns:
        return

    try:
        pk_cols_str = '", "'.join(pk_columns)
        pk_name = f"pk_{table_name}"[:63]
        
        alter_sql = f"""
            ALTER TABLE "{db_name}"."{table_name}"
            ADD CONSTRAINT "{pk_name}" PRIMARY KEY ("{pk_cols_str}");
        """
        with pg_engine.connect() as conn:
            conn.execute(text(alter_sql))
            conn.commit()
            logger.info(f"    + PK restaurada: ({pk_cols_str})")
    except Exception as e:
        logger.warning(f"    ! Falló restaurar PK {table_name}: {e}")

def migrate_table_attempt(mssql_engine, pg_engine, db_name, table_name, chunk_size, pk_columns):
    inspector = inspect(mssql_engine)
    columns_info = inspector.get_columns(table_name)
    dtype_mapping = {col['name']: get_precise_type(col['type']) for col in columns_info}

    query = f"SELECT * FROM [{table_name}]"
    chunks = pd.read_sql_query(query, mssql_engine, chunksize=chunk_size)
    
    total_rows = 0
    is_first_chunk = True
    
    for i, df_chunk in enumerate(chunks):
        if df_chunk.empty: continue

        # --- FIX CRÍTICO: DROP CASCADE ---
        # Rompe las FKs que impiden borrar la tabla vieja
        if is_first_chunk:
            try:
                drop_sql = f'DROP TABLE IF EXISTS "{db_name}"."{table_name}" CASCADE'
                with pg_engine.connect() as conn:
                    conn.execute(text(drop_sql))
                    conn.commit()
            except Exception as e:
                logger.warning(f"    ! Advertencia al dropear {table_name}: {e}")
        # ---------------------------------

        df_chunk = clean_dataframe(df_chunk, dtype_mapping)
        
        # Como ya borramos manualmente arriba, usamos 'replace' para crear estructura,
        # o 'append' para los siguientes chunks.
        mode = 'replace' if is_first_chunk else 'append'
        
        df_chunk.to_sql(
            table_name, pg_engine, schema=db_name, if_exists=mode, 
            index=False, method='multi', chunksize=1000, dtype=dtype_mapping
        )
        
        total_rows += len(df_chunk)
        is_first_chunk = False
        
        if (i + 1) % 10 == 0:
            logger.info(f"    -> {table_name}: {total_rows} filas...")

    if total_rows > 0:
        restore_primary_key(pg_engine, db_name, table_name, pk_columns)
    
    return total_rows

def migrate_table_with_retry(mssql_engine, pg_engine, db_name, table_name):
    current_chunk = INITIAL_CHUNK_SIZE
    
    pk_columns = get_pk_columns_raw(mssql_engine, table_name)
    harvest_foreign_keys(mssql_engine, db_name, table_name)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if attempt > 1:
                logger.info(f"    [RETRY {attempt}/{MAX_RETRIES}] {table_name} Chunk={current_chunk}...")
            
            rows = migrate_table_attempt(mssql_engine, pg_engine, db_name, table_name, current_chunk, pk_columns)
            
            pk_msg = f"PK: {pk_columns}" if pk_columns else "SIN PK"
            if rows > 0:
                logger.info(f"    [OK] {table_name}: {rows} filas. ({pk_msg})")
            else:
                logger.info(f"    [SKIP] {table_name} vacía.")
            return

        except Exception as e:
            logger.error(f"    [ERROR] {table_name} (Intento {attempt}): {e}")
            if attempt == MAX_RETRIES:
                logger.critical(f"    !!! SE RINDIÓ CON {table_name} DESPUÉS DE {MAX_RETRIES} INTENTOS.")
                return
            
            wait_time = attempt * 5
            current_chunk = max(MIN_CHUNK_SIZE, int(current_chunk / 2))
            time.sleep(wait_time)

def apply_pending_foreign_keys(pg_engine, db_name):
    if db_name not in PENDING_FKS or not PENDING_FKS[db_name]:
        return

    logger.info(f"--- Aplicando Foreign Keys para: {db_name} ---")
    fks_list = PENDING_FKS[db_name]
    success = 0
    
    with pg_engine.connect() as conn:
        for fk in fks_list:
            try:
                conn.execute(text(fk['sql']))
                conn.commit()
                success += 1
            except Exception:
                pass
    
    logger.info(f"    -> FKs aplicadas: {success}/{len(fks_list)}")

def process_database_full(db_name, pg_engine):
    PENDING_FKS[db_name] = []
    
    with pg_engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS \"{db_name}\""))
        conn.commit()

    mssql_engine = get_mssql_engine(db_name)
    
    # Test conexión
    with mssql_engine.connect() as test_conn:
        pass
    
    inspector = inspect(mssql_engine)
    tables = inspector.get_table_names()

    for table in tables:
        migrate_table_with_retry(mssql_engine, pg_engine, db_name, table)
    
    apply_pending_foreign_keys(pg_engine, db_name)

def migrate():
    logger.info(f"Iniciando migración MODO TANQUE (Retries={MAX_RETRIES}, NullPool + CASCADE)...")
    pg_engine = get_pg_engine()

    for db_name in SOURCE_DBS:
        logger.info(f"=== INICIANDO DB: {db_name} ===")
        
        db_success = False
        
        for db_attempt in range(1, DB_MAX_RETRIES + 1):
            try:
                if db_attempt > 1:
                    logger.warning(f"Reintentando conexión a DB {db_name} (Intento {db_attempt}/{DB_MAX_RETRIES})...")
                
                process_database_full(db_name, pg_engine)
                db_success = True
                break

            except Exception as e:
                logger.error(f"FALLO CRÍTICO en DB {db_name} (Intento {db_attempt}): {e}")
                time.sleep(10 * db_attempt)
        
        if not db_success:
            logger.critical(f"!!! ABANDONANDO DB {db_name}.")

    logger.info("Migración Finalizada.")

if __name__ == "__main__":
    migrate()