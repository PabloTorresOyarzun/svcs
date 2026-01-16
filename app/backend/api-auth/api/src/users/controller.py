from litestar import Controller, get, post, put, delete
from litestar.params import Parameter
from litestar.exceptions import HTTPException
from litestar.openapi.spec import Tag

from src.users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    PasswordChange,
)
from src.users.service import get_user_service, UserServiceError


class UserController(Controller):
    """
    Controller REST para gestion de usuarios.
    Intermediario entre aplicaciones cliente y Keycloak.
    """

    path = "/users"
    tags = ["Usuarios"]

    @post(
        path="/",
        summary="Crear usuario",
        description="Crea un nuevo usuario en el sistema de autenticacion y sincroniza con la base de datos de negocio.",
        status_code=201,
    )
    async def create_user(self, data: UserCreate) -> UserResponse:
        try:
            service = get_user_service()
            return await service.create_user(data)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/",
        summary="Listar usuarios",
        description="Obtiene una lista paginada de usuarios.",
    )
    async def list_users(
        self,
        page: int = Parameter(default=1, ge=1, description="Numero de pagina"),
        page_size: int = Parameter(default=20, ge=1, le=100, description="Resultados por pagina"),
        search: str | None = Parameter(default=None, description="Buscar por nombre, email o username"),
    ) -> UserListResponse:
        try:
            service = get_user_service()
            return await service.list_users(page=page, page_size=page_size, search=search)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @get(
        path="/{user_id:str}",
        summary="Obtener usuario",
        description="Obtiene los datos de un usuario por su ID.",
    )
    async def get_user(self, user_id: str) -> UserResponse:
        try:
            service = get_user_service()
            return await service.get_user(user_id)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @put(
        path="/{user_id:str}",
        summary="Actualizar usuario",
        description="Actualiza los datos de un usuario existente.",
    )
    async def update_user(self, user_id: str, data: UserUpdate) -> UserResponse:
        try:
            service = get_user_service()
            return await service.update_user(user_id, data)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @delete(
        path="/{user_id:str}",
        summary="Eliminar usuario",
        description="Elimina un usuario del sistema.",
        status_code=204,
    )
    async def delete_user(self, user_id: str) -> None:
        try:
            service = get_user_service()
            await service.delete_user(user_id)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @put(
        path="/{user_id:str}/password",
        summary="Cambiar contraseña",
        description="Establece una nueva contraseña para el usuario.",
        status_code=204,
    )
    async def change_password(self, user_id: str, data: PasswordChange) -> None:
        try:
            service = get_user_service()
            await service.change_password(user_id, data)
        except UserServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)