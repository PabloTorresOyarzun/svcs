from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    """Schema para creacion de rol."""

    name: str = Field(..., min_length=2, max_length=100)
    description: str = Field("", max_length=255)


class RoleUpdate(BaseModel):
    """Schema para actualizacion de rol."""

    description: str | None = Field(None, max_length=255)


class RoleResponse(BaseModel):
    """Schema de respuesta de rol."""

    id: str
    name: str
    description: str


class RoleListResponse(BaseModel):
    """Schema de respuesta para lista de roles."""

    roles: list[RoleResponse]
    total: int


class UserRoleAssignment(BaseModel):
    """Schema para asignar/desasignar rol a usuario."""

    role_name: str