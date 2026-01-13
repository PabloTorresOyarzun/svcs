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
        Crea la tabla de usuarios si no existe.
        Esta tabla es una proyeccion de solo lectura para la base de negocio.
        """
        create_table_sql = text("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                full_name VARCHAR(200),
                synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP NULL
            )
        """)

        create_index_email = text(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )

        create_index_deleted = text(
            "CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at)"
        )

        async with self.engine.begin() as conn:
            await conn.execute(create_table_sql)
            await conn.execute(create_index_email)
            await conn.execute(create_index_deleted)
            logger.info("users_table_ensured")

    async def sync_user(self, user_id: str, email: str, full_name: str) -> None:
        """
        Sincroniza o actualiza un usuario en la base de negocio.
        Usa UPSERT para manejar creacion y actualizacion.
        """
        upsert_sql = text("""
            INSERT INTO users (id, email, full_name, synced_at, deleted_at)
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
            logger.info("user_synced", user_id=user_id)

    async def delete_user(self, user_id: str) -> None:
        """
        Marca un usuario como eliminado (soft delete).
        No elimina fisicamente para mantener integridad referencial.
        """
        soft_delete_sql = text("""
            UPDATE users 
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
            logger.info("user_soft_deleted", user_id=user_id)

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