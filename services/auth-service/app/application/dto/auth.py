from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Email del usuario.", examples=["ana@ikbo.co"])
    password: str = Field(..., description="Contrasena del usuario.", examples=["secret123"])
    tenant_slug: Optional[str] = Field(
        None,
        description="Slug del tenant. Requerido si no viene el header X-Tenant-Slug (modo API client).",
        examples=["ikbo"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {"email": "ana@ikbo.co", "password": "secret123", "tenant_slug": "ikbo"}
        }
    }


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_slug: str
    roles: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token emitido en el login.")

    model_config = {"json_schema_extra": {"example": {"refresh_token": "eyJ..."}}}


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
