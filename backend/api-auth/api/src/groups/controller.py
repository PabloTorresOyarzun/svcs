from litestar import Controller, get, post, put, delete
from litestar.exceptions import HTTPException

from src.auth.keycloak import get_keycloak_client, KeycloakAdminError
from src.groups.schemas import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    GroupListResponse,
    GroupMemberResponse,
    GroupMembersResponse,
    UserGroupAssignment,
)


def _map_group(kc_group: dict) -> GroupResponse:
    """Mapea grupo de Keycloak a schema de respuesta."""
    subgroups = [_map_group(sg) for sg in kc_group.get("subGroups", [])]
    return GroupResponse(
        id=kc_group.get("id", ""),
        name=kc_group.get("name", ""),
        path=kc_group.get("path", ""),
        subgroups=subgroups,
    )


class GroupController(Controller):
    """Controller REST para gestion de grupos."""

    path = "/groups"
    tags = ["Grupos"]

    @post(
        path="/",
        summary="Crear grupo",
        description="Crea un nuevo grupo o subgrupo.",
        status_code=201,
    )
    async def create_group(self, data: GroupCreate) -> GroupResponse:
        try:
            keycloak = get_keycloak_client()
            group_id = await keycloak.create_group(name=data.name, parent_id=data.parent_id)
            group = await keycloak.get_group(group_id)
            return _map_group(group)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/",
        summary="Listar grupos",
        description="Obtiene todos los grupos del realm con sus subgrupos.",
    )
    async def list_groups(self) -> GroupListResponse:
        try:
            keycloak = get_keycloak_client()
            kc_groups = await keycloak.list_groups()
            groups = [_map_group(g) for g in kc_groups]
            return GroupListResponse(groups=groups, total=len(groups))
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/{group_id:str}",
        summary="Obtener grupo",
        description="Obtiene un grupo por ID.",
    )
    async def get_group(self, group_id: str) -> GroupResponse:
        try:
            keycloak = get_keycloak_client()
            group = await keycloak.get_group(group_id)
            return _map_group(group)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @put(
        path="/{group_id:str}",
        summary="Actualizar grupo",
        description="Actualiza el nombre de un grupo.",
    )
    async def update_group(self, group_id: str, data: GroupUpdate) -> GroupResponse:
        try:
            keycloak = get_keycloak_client()
            await keycloak.update_group(group_id, data.name)
            group = await keycloak.get_group(group_id)
            return _map_group(group)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @delete(
        path="/{group_id:str}",
        summary="Eliminar grupo",
        description="Elimina un grupo y todos sus subgrupos.",
        status_code=204,
    )
    async def delete_group(self, group_id: str) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.delete_group(group_id)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/{group_id:str}/members",
        summary="Obtener miembros",
        description="Obtiene los miembros de un grupo.",
    )
    async def get_members(self, group_id: str) -> GroupMembersResponse:
        try:
            keycloak = get_keycloak_client()
            kc_members = await keycloak.get_group_members(group_id)
            members = [
                GroupMemberResponse(
                    id=m.get("id", ""),
                    username=m.get("username", ""),
                    email=m.get("email", ""),
                    first_name=m.get("firstName", ""),
                    last_name=m.get("lastName", ""),
                )
                for m in kc_members
            ]
            return GroupMembersResponse(members=members, total=len(members))
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)


class UserGroupController(Controller):
    """Controller REST para asignacion de usuarios a grupos."""

    path = "/users/{user_id:str}/groups"
    tags = ["Usuarios", "Grupos"]

    @get(
        path="/",
        summary="Obtener grupos de usuario",
        description="Obtiene los grupos a los que pertenece un usuario.",
    )
    async def get_user_groups(self, user_id: str) -> GroupListResponse:
        try:
            keycloak = get_keycloak_client()
            kc_groups = await keycloak.get_user_groups(user_id)
            groups = [_map_group(g) for g in kc_groups]
            return GroupListResponse(groups=groups, total=len(groups))
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @post(
        path="/",
        summary="Agregar usuario a grupo",
        description="Agrega un usuario a un grupo.",
        status_code=204,
    )
    async def add_to_group(self, user_id: str, data: UserGroupAssignment) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.add_user_to_group(user_id, data.group_id)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @delete(
        path="/{group_id:str}",
        summary="Remover usuario de grupo",
        description="Remueve un usuario de un grupo.",
        status_code=204,
    )
    async def remove_from_group(self, user_id: str, group_id: str) -> None:
        try:
            keycloak = get_keycloak_client()
            await keycloak.remove_user_from_group(user_id, group_id)
        except KeycloakAdminError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)