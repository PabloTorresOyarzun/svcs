import logging
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_db() -> SQLDatabase:
    """
    Creates and returns a SQLDatabase instance for LangChain.
    Uses synchronous PostgreSQL driver for LangChain compatibility.
    """
    db_url = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    
    logger.info(f"Connecting to database schema: {settings.DB_SCHEMA}")
    engine = create_engine(db_url)
    return SQLDatabase(engine, schema=settings.DB_SCHEMA)
