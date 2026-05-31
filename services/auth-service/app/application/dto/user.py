from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class InviteUserRequest(BaseModel):
    email: EmailStr = Field(
        ..., description="Email del nuevo usuario.", examples=["operador@ikbo.co"]
    )
    full_name: Optional[str] = Field(
        None, description="Nombre completo.", examples=["Carlos Perez"]
    )
    password: str = Field(
        ..., min_length=8, description="Contrasena inicial.", examples=["Initial123!"]
    )
    role: Literal["tenant_admin", "operator", "viewer"] = Field(
        "operator",
        description="Rol asignado al usuario dentro del tenant.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "operador@ikbo.co",
                "full_name": "Carlos Perez",
                "password": "Initial123!",
                "role": "operator",
            }
        }
    }


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    roles: list[str] = []

    model_config = {"from_attributes": True}
