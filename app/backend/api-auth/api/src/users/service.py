from datetime import datetime
import structlog

from src.auth.keycloak import get_keycloak_client, KeycloakAdminError
from src.sync.user_sync import get_user_sync_service
from src.users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    PasswordChange,
)

logger = structlog.get_logger()


class UserServiceError(Exception):
    """Error en operacion de servicio de usuarios."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UserService:
    """
    Servicio de gestion de usuarios.
    Orquesta operaciones entre Keycloak y la base de datos de negocio.
    """

    def __init__(self):
        self.keycloak = get_keycloak_client()
        self.sync_service = get_user_sync_service()

    def _map_keycloak_user(self, kc_user: dict) -> UserResponse:
        """Mapea usuario de Keycloak a schema de respuesta."""
        created_timestamp = kc_user.get("createdTimestamp")
        created_at = None
        if created_timestamp:
            created_at = datetime.fromtimestamp(created_timestamp / 1000)

        return UserResponse(
            id=kc_user["id"],
            username=kc_user.get("username", ""),
            email=kc_user.get("email", ""),
            first_name=kc_user.get("firstName", ""),
            last_name=kc_user.get("lastName", ""),
            enabled=kc_user.get("enabled", False),
            email_verified=kc_user.get("emailVerified", False),
            created_at=created_at,
        )

    async def create_user(self, data: UserCreate) -> UserResponse:
        """
        Crea un nuevo usuario en Keycloak y sincroniza con base de negocio.
        """
        try:
            # Crear en Keycloak
            user_id = await self.keycloak.create_user(
                username=data.username,
                email=data.email,
                password=data.password,
                first_name=data.first_name,
                last_name=data.last_name,
            )

            # Obtener datos completos
            kc_user = await self.keycloak.get_user(user_id)
            user = self._map_keycloak_user(kc_user)

            # Sincronizar con base de negocio
            await self.sync_service.sync_user(
                user_id=user.id,
                email=user.email,
                full_name=f"{user.first_name} {user.last_name}".strip(),
            )

            logger.info("user_created_and_synced", user_id=user_id)
            return user

        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)

    async def get_user(self, user_id: str) -> UserResponse:
        """Obtiene un usuario por ID."""
        try:
            kc_user = await self.keycloak.get_user(user_id)
            return self._map_keycloak_user(kc_user)
        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)

    async def update_user(self, user_id: str, data: UserUpdate) -> UserResponse:
        """
        Actualiza un usuario en Keycloak y sincroniza cambios.
        """
        try:
            await self.keycloak.update_user(
                user_id=user_id,
                email=data.email,
                first_name=data.first_name,
                last_name=data.last_name,
                enabled=data.enabled,
            )

            # Obtener datos actualizados
            kc_user = await self.keycloak.get_user(user_id)
            user = self._map_keycloak_user(kc_user)

            # Sincronizar cambios
            await self.sync_service.sync_user(
                user_id=user.id,
                email=user.email,
                full_name=f"{user.first_name} {user.last_name}".strip(),
            )

            return user

        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)

    async def delete_user(self, user_id: str) -> None:
        """
        Elimina un usuario de Keycloak y marca como eliminado en base de negocio.
        """
        try:
            await self.keycloak.delete_user(user_id)
            await self.sync_service.delete_user(user_id)
        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> UserListResponse:
        """Lista usuarios con paginacion."""
        try:
            first = (page - 1) * page_size
            kc_users = await self.keycloak.list_users(
                first=first,
                max_results=page_size,
                search=search,
            )

            users = [self._map_keycloak_user(u) for u in kc_users]

            return UserListResponse(
                users=users,
                total=len(users),  # Keycloak no retorna total real
                page=page,
                page_size=page_size,
            )

        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)

    async def change_password(self, user_id: str, data: PasswordChange) -> None:
        """Cambia la contraseña de un usuario."""
        try:
            await self.keycloak.set_password(user_id, data.new_password)
        except KeycloakAdminError as e:
            raise UserServiceError(e.message, e.status_code)


# Singleton
_user_service: UserService | None = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service