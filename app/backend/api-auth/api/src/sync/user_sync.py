from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from datetime import datetime
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class UserSyncService:
    """
    Servicio de sincronizacion de usuarios con la base de datos de negocio.
    Mantiene una proyeccion minima de usuarios para reportes y queries.
    """

    def __init__(self):
        self.settings = get_settings()
        # Leemos el esquema desde la configuración
        self.schema = self.settings.business_db_schema
        
        self.engine = create_async_engine(
            self.settings.business_db_url,
            echo=self.settings.app_debug,
            pool_size=5,
            max_overflow=10,
        )
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def ensure_table_exists(self) -> None:
        """
        Crea el esquema y la tabla de usuarios si no existen.
        Esta tabla es una proyeccion de solo lectura para la base de negocio.
        """
        # 1. Asegurar que el esquema existe
        create_schema_sql = text(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

        # 2. Crear la tabla dentro del esquema configurado
        create_table_sql = text(f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.users (
                id UUID PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                full_name VARCHAR(200),
                synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP NULL
            )
        """)

        # 3. Indices con el prefijo del esquema
        create_index_email = text(
            f"CREATE INDEX IF NOT EXISTS idx_users_email ON {self.schema}.users(email)"
        )

        create_index_deleted = text(
            f"CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON {self.schema}.users(deleted_at)"
        )

        async with self.engine.begin() as conn:
            await conn.execute(create_schema_sql)
            await conn.execute(create_table_sql)
            await conn.execute(create_index_email)
            await conn.execute(create_index_deleted)
            logger.info("users_table_ensured", schema=self.schema)

    async def sync_user(self, user_id: str, email: str, full_name: str) -> None:
        """
        Sincroniza o actualiza un usuario en la base de negocio.
        Usa UPSERT para manejar creacion y actualizacion.
        """
        # Inserción apuntando al esquema configurado
        upsert_sql = text(f"""
            INSERT INTO {self.schema}.users (id, email, full_name, synced_at, deleted_at)
            VALUES (:id, :email, :full_name, :synced_at, NULL)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                full_name = EXCLUDED.full_name,
                synced_at = EXCLUDED.synced_at,
                deleted_at = NULL
        """)

        async with self.async_session() as session:
            await session.execute(
                upsert_sql,
                {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "synced_at": datetime.utcnow(),
                },
            )
            await session.commit()
            logger.info("user_synced", user_id=user_id, schema=self.schema)

    async def delete_user(self, user_id: str) -> None:
        """
        Marca un usuario como eliminado (soft delete).
        No elimina fisicamente para mantener integridad referencial.
        """
        soft_delete_sql = text(f"""
            UPDATE {self.schema}.users 
            SET deleted_at = :deleted_at
            WHERE id = :id
        """)

        async with self.async_session() as session:
            await session.execute(
                soft_delete_sql,
                {
                    "id": user_id,
                    "deleted_at": datetime.utcnow(),
                },
            )
            await session.commit()
            logger.info("user_soft_deleted", user_id=user_id, schema=self.schema)

    async def close(self) -> None:
        """Cierra las conexiones a la base de datos."""
        await self.engine.dispose()


# Singleton
_sync_service: UserSyncService | None = None


def get_user_sync_service() -> UserSyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = UserSyncService()
    return _sync_service