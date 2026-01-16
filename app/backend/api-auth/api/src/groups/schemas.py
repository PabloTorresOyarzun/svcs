from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    """Schema para creacion de grupo."""

    name: str = Field(..., min_length=2, max_length=100)
    parent_id: str | None = Field(None, description="ID del grupo padre para crear subgrupo")


class GroupUpdate(BaseModel):
    """Schema para actualizacion de grupo."""

    name: str = Field(..., min_length=2, max_length=100)


class GroupResponse(BaseModel):
    """Schema de respuesta de grupo."""

    id: str
    name: str
    path: str
    subgroups: list["GroupResponse"] = []


class GroupListResponse(BaseModel):
    """Schema de respuesta para lista de grupos."""

    groups: list[GroupResponse]
    total: int


class GroupMemberResponse(BaseModel):
    """Schema de respuesta para miembro de grupo."""

    id: str
    username: str
    email: str
    first_name: str
    last_name: str


class GroupMembersResponse(BaseModel):
    """Schema de respuesta para lista de miembros."""

    members: list[GroupMemberResponse]
    total: int


class UserGroupAssignment(BaseModel):
    """Schema para agregar/remover usuario de grupo."""

    group_id: str