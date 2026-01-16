from litestar import Controller, get, post, put, delete
from litestar.exceptions import HTTPException

from src.auth.keycloak import get_keycloak_client, KeycloakAdminError
from src.roles.schemas import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    UserRoleAssignment,
)


class RoleController(Controller):
    """Controller REST para gestion de roles."""

    path = "/roles"
    tags = ["Roles"]

    @post(
        path="/",
        summary="Crear rol",
        description="Crea un nuevo rol en el realm.",
        status_code=201,
    )
    async def create_role(self, data: RoleCreate) -> dict:
        try:
            keycloak = get_keycloak_client()
            await keycloak.create_role(name=data.name, description=data.description)
            return {"message": f"Role '{data.name}' created successfully"}
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/",
        summary="Listar roles",
        description="Obtiene todos los roles del realm.",
    )
    async def list_roles(self) -> RoleListResponse:
        try:
            keycloak = get_keycloak_client()
            kc_roles = await keycloak.list_roles()
            roles = [
                RoleResponse(
                    id=r.get("id", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                )
                for r in kc_roles
                if not r.get("name", "").startswith("default-roles-")
            ]
            return RoleListResponse(roles=roles, total=len(roles))
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/{role_name:str}",
        summary="Obtener rol",
        description="Obtiene un rol por nombre.",
    )
    async def get_role(self, role_name: str) -> RoleResponse:
        try:
            keycloak = get_keycloak_client()
            role = await keycloak.get_role(role_name)
            return RoleResponse(
                id=role.get("id", ""),
                name=role.get("name", ""),
                description=role.get("description", ""),
            )
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @put(
        path="/{role_name:str}",
        summary="Actualizar rol",
        description="Actualiza la descripcion de un rol.",
    )
    async def update_role(self, role_name: str, data: RoleUpdate) -> RoleResponse:
        try:
            keycloak = get_keycloak_client()
            if data.description is not None:
                await keycloak.update_role(role_name, data.description)
            role = await keycloak.get_role(role_name)
            return RoleResponse(
                id=role.get("id", ""),
                name=role.get("name", ""),
                description=role.get("description", ""),
            )
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @delete(
        path="/{role_name:str}",
        summary="Eliminar rol",
        description="Elimina un rol del realm.",
        status_code=204,
    )
    async def delete_role(self, role_name: str) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.delete_role(role_name)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)


class UserRoleController(Controller):
    """Controller REST para asignacion de roles a usuarios."""

    path = "/users/{user_id:str}/roles"
    tags = ["Usuarios", "Roles"]

    @get(
        path="/",
        summary="Obtener roles de usuario",
        description="Obtiene los roles asignados a un usuario.",
    )
    async def get_user_roles(self, user_id: str) -> RoleListResponse:
        try:
            keycloak = get_keycloak_client()
            kc_roles = await keycloak.get_user_roles(user_id)
            roles = [
                RoleResponse(
                    id=r.get("id", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                )
                for r in kc_roles
                if not r.get("name", "").startswith("default-roles-")
            ]
            return RoleListResponse(roles=roles, total=len(roles))
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @post(
        path="/",
        summary="Asignar rol a usuario",
        description="Asigna un rol a un usuario.",
        status_code=204,
    )
    async def assign_role(self, user_id: str, data: UserRoleAssignment) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.assign_role_to_user(user_id, data.role_name)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @delete(
        path="/{role_name:str}",
        summary="Remover rol de usuario",
        description="Remueve un rol de un usuario.",
        status_code=204,
    )
    async def remove_role(self, user_id: str, role_name: str) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.remove_role_from_user(user_id, role_name)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)