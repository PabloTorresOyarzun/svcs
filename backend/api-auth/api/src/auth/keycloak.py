import httpx
from typing import Any
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class KeycloakAdminError(Exception):
    """Error en operacion con Keycloak Admin API."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class KeycloakAdminClient:
    """
    Cliente para interactuar con la Admin REST API de Keycloak.
    Maneja autenticacion y operaciones CRUD de usuarios.
    """

    def __init__(self):
        self.settings = get_settings()
        self._access_token: str | None = None

    async def _get_admin_token(self) -> str:
        """Obtiene token de acceso para la Admin API."""
        token_url = f"{self.settings.keycloak_url}/realms/master/protocol/openid-connect/token"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": self.settings.keycloak_admin_user,
                        "password": self.settings.keycloak_admin_password,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["access_token"]

            except httpx.HTTPStatusError as e:
                logger.error("admin_token_failed", status=e.response.status_code)
                raise KeycloakAdminError("Failed to obtain admin token", 503)
            except httpx.HTTPError as e:
                logger.error("admin_token_error", error=str(e))
                raise KeycloakAdminError("Keycloak connection error", 503)

    async def _get_headers(self) -> dict[str, str]:
        """Obtiene headers con token de autorizacion."""
        if self._access_token is None:
            self._access_token = await self._get_admin_token()

        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        """Ejecuta request a la Admin API con manejo de token expirado."""
        url = f"{self.settings.keycloak_admin_url}/{endpoint}"
        headers = await self._get_headers()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    timeout=15.0,
                )

                # Token expirado, reintentar
                if response.status_code == 401 and retry:
                    self._access_token = None
                    return await self._request(method, endpoint, json_data, retry=False)

                return response

            except httpx.HTTPError as e:
                logger.error("keycloak_request_error", error=str(e), endpoint=endpoint)
                raise KeycloakAdminError("Keycloak connection error", 503)

    # ----------------------------------------------------------------
    # Operaciones CRUD de usuarios
    # ----------------------------------------------------------------

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        enabled: bool = True,
    ) -> str:
        """
        Crea un nuevo usuario en Keycloak.

        Returns:
            ID del usuario creado
        """
        user_data = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": enabled,
            "emailVerified": False,
            "credentials": [
                {
                    "type": "password",
                    "value": password,
                    "temporary": False,
                }
            ],
        }

        response = await self._request("POST", "users", user_data)

        if response.status_code == 201:
            # Extraer ID del header Location
            location = response.headers.get("Location", "")
            user_id = location.split("/")[-1]
            logger.info("user_created", user_id=user_id, username=username)
            return user_id

        if response.status_code == 409:
            raise KeycloakAdminError("User already exists", 409)

        error = response.json().get("errorMessage", "Unknown error")
        raise KeycloakAdminError(f"Failed to create user: {error}", response.status_code)

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """Obtiene un usuario por ID."""
        response = await self._request("GET", f"users/{user_id}")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to get user", response.status_code)

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Busca un usuario por email."""
        response = await self._request("GET", f"users?email={email}&exact=true")

        if response.status_code == 200:
            users = response.json()
            return users[0] if users else None

        raise KeycloakAdminError("Failed to search user", response.status_code)

    async def update_user(
        self,
        user_id: str,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Actualiza datos de un usuario."""
        update_data = {}
        if email is not None:
            update_data["email"] = email
        if first_name is not None:
            update_data["firstName"] = first_name
        if last_name is not None:
            update_data["lastName"] = last_name
        if enabled is not None:
            update_data["enabled"] = enabled

        if not update_data:
            return

        response = await self._request("PUT", f"users/{user_id}", update_data)

        if response.status_code == 204:
            logger.info("user_updated", user_id=user_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to update user", response.status_code)

    async def delete_user(self, user_id: str) -> None:
        """Elimina un usuario."""
        response = await self._request("DELETE", f"users/{user_id}")

        if response.status_code == 204:
            logger.info("user_deleted", user_id=user_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to delete user", response.status_code)

    async def list_users(
        self,
        first: int = 0,
        max_results: int = 100,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista usuarios con paginacion."""
        params = f"first={first}&max={max_results}"
        if search:
            params += f"&search={search}"

        response = await self._request("GET", f"users?{params}")

        if response.status_code == 200:
            return response.json()

        raise KeycloakAdminError("Failed to list users", response.status_code)

    async def set_password(self, user_id: str, password: str, temporary: bool = False) -> None:
        """Establece una nueva contraseña para el usuario."""
        credential_data = {
            "type": "password",
            "value": password,
            "temporary": temporary,
        }

        response = await self._request("PUT", f"users/{user_id}/reset-password", credential_data)

        if response.status_code == 204:
            logger.info("password_reset", user_id=user_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to reset password", response.status_code)

    # ----------------------------------------------------------------
    # Operaciones CRUD de roles
    # ----------------------------------------------------------------

    async def create_role(self, name: str, description: str = "") -> None:
        """Crea un nuevo rol en el realm."""
        role_data = {
            "name": name,
            "description": description,
        }

        response = await self._request("POST", "roles", role_data)

        if response.status_code == 201:
            logger.info("role_created", role_name=name)
            return

        if response.status_code == 409:
            raise KeycloakAdminError("Role already exists", 409)

        error = response.json().get("errorMessage", "Unknown error")
        raise KeycloakAdminError(f"Failed to create role: {error}", response.status_code)

    async def get_role(self, role_name: str) -> dict[str, Any]:
        """Obtiene un rol por nombre."""
        response = await self._request("GET", f"roles/{role_name}")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("Role not found", 404)

        raise KeycloakAdminError("Failed to get role", response.status_code)

    async def update_role(self, role_name: str, description: str) -> None:
        """Actualiza la descripcion de un rol."""
        role_data = {
            "name": role_name,
            "description": description,
        }

        response = await self._request("PUT", f"roles/{role_name}", role_data)

        if response.status_code == 204:
            logger.info("role_updated", role_name=role_name)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("Role not found", 404)

        raise KeycloakAdminError("Failed to update role", response.status_code)

    async def delete_role(self, role_name: str) -> None:
        """Elimina un rol."""
        response = await self._request("DELETE", f"roles/{role_name}")

        if response.status_code == 204:
            logger.info("role_deleted", role_name=role_name)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("Role not found", 404)

        raise KeycloakAdminError("Failed to delete role", response.status_code)

    async def list_roles(self) -> list[dict[str, Any]]:
        """Lista todos los roles del realm."""
        response = await self._request("GET", "roles")

        if response.status_code == 200:
            return response.json()

        raise KeycloakAdminError("Failed to list roles", response.status_code)

    async def assign_role_to_user(self, user_id: str, role_name: str) -> None:
        """Asigna un rol a un usuario."""
        role = await self.get_role(role_name)
        role_data = [{"id": role["id"], "name": role["name"]}]

        response = await self._request("POST", f"users/{user_id}/role-mappings/realm", role_data)

        if response.status_code == 204:
            logger.info("role_assigned", user_id=user_id, role_name=role_name)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to assign role", response.status_code)

    async def remove_role_from_user(self, user_id: str, role_name: str) -> None:
        """Remueve un rol de un usuario."""
        role = await self.get_role(role_name)
        role_data = [{"id": role["id"], "name": role["name"]}]

        response = await self._request("DELETE", f"users/{user_id}/role-mappings/realm", role_data)

        if response.status_code == 204:
            logger.info("role_removed", user_id=user_id, role_name=role_name)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User or role not found", 404)

        raise KeycloakAdminError("Failed to remove role", response.status_code)

    async def get_user_roles(self, user_id: str) -> list[dict[str, Any]]:
        """Obtiene los roles asignados a un usuario."""
        response = await self._request("GET", f"users/{user_id}/role-mappings/realm")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to get user roles", response.status_code)

    # ----------------------------------------------------------------
    # Operaciones CRUD de grupos
    # ----------------------------------------------------------------

    async def create_group(self, name: str, parent_id: str | None = None) -> str:
        """Crea un nuevo grupo. Si parent_id se especifica, crea un subgrupo."""
        group_data = {"name": name}

        if parent_id:
            endpoint = f"groups/{parent_id}/children"
        else:
            endpoint = "groups"

        response = await self._request("POST", endpoint, group_data)

        if response.status_code == 201:
            location = response.headers.get("Location", "")
            group_id = location.split("/")[-1]
            logger.info("group_created", group_id=group_id, name=name, parent_id=parent_id)
            return group_id

        if response.status_code == 409:
            raise KeycloakAdminError("Group already exists", 409)

        error = response.json().get("errorMessage", "Unknown error")
        raise KeycloakAdminError(f"Failed to create group: {error}", response.status_code)

    async def get_group(self, group_id: str) -> dict[str, Any]:
        """Obtiene un grupo por ID."""
        response = await self._request("GET", f"groups/{group_id}")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("Group not found", 404)

        raise KeycloakAdminError("Failed to get group", response.status_code)

    async def update_group(self, group_id: str, name: str) -> None:
        """Actualiza el nombre de un grupo."""
        group_data = {"name": name}

        response = await self._request("PUT", f"groups/{group_id}", group_data)

        if response.status_code == 204:
            logger.info("group_updated", group_id=group_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("Group not found", 404)

        raise KeycloakAdminError("Failed to update group", response.status_code)

    async def delete_group(self, group_id: str) -> None:
        """Elimina un grupo."""
        response = await self._request("DELETE", f"groups/{group_id}")

        if response.status_code == 204:
            logger.info("group_deleted", group_id=group_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("Group not found", 404)

        raise KeycloakAdminError("Failed to delete group", response.status_code)

    async def list_groups(self) -> list[dict[str, Any]]:
        """Lista todos los grupos del realm (incluye subgrupos anidados)."""
        response = await self._request("GET", "groups")

        if response.status_code == 200:
            return response.json()

        raise KeycloakAdminError("Failed to list groups", response.status_code)

    async def add_user_to_group(self, user_id: str, group_id: str) -> None:
        """Agrega un usuario a un grupo."""
        response = await self._request("PUT", f"users/{user_id}/groups/{group_id}")

        if response.status_code == 204:
            logger.info("user_added_to_group", user_id=user_id, group_id=group_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User or group not found", 404)

        raise KeycloakAdminError("Failed to add user to group", response.status_code)

    async def remove_user_from_group(self, user_id: str, group_id: str) -> None:
        """Remueve un usuario de un grupo."""
        response = await self._request("DELETE", f"users/{user_id}/groups/{group_id}")

        if response.status_code == 204:
            logger.info("user_removed_from_group", user_id=user_id, group_id=group_id)
            return

        if response.status_code == 404:
            raise KeycloakAdminError("User or group not found", 404)

        raise KeycloakAdminError("Failed to remove user from group", response.status_code)

    async def get_user_groups(self, user_id: str) -> list[dict[str, Any]]:
        """Obtiene los grupos a los que pertenece un usuario."""
        response = await self._request("GET", f"users/{user_id}/groups")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("User not found", 404)

        raise KeycloakAdminError("Failed to get user groups", response.status_code)

    async def get_group_members(self, group_id: str) -> list[dict[str, Any]]:
        """Obtiene los miembros de un grupo."""
        response = await self._request("GET", f"groups/{group_id}/members")

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise KeycloakAdminError("Group not found", 404)

        raise KeycloakAdminError("Failed to get group members", response.status_code)


# Singleton
_keycloak_client: KeycloakAdminClient | None = None


def get_keycloak_client() -> KeycloakAdminClient:
    global _keycloak_client
    if _keycloak_client is None:
        _keycloak_client = KeycloakAdminClient()
    return _keycloak_client