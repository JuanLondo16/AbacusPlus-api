import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


class RegisterTenantRequest(BaseModel):
    slug: str = Field(
        ...,
        description="Identificador unico del tenant (minusculas, sin espacios). Se usa como nombre de la DB: abacus_t_{slug}.",
        examples=["ikbo"],
    )
    display_name: str = Field(
        ..., description="Nombre visible de la empresa.", examples=["IKBO SAS"]
    )
    email_domain: Optional[str] = Field(
        None,
        description="Dominio de email de la empresa para auto-detectar el tenant en login.",
        examples=["ikbo.co"],
    )
    admin_email: EmailStr = Field(
        ..., description="Email del primer usuario administrador.", examples=["admin@ikbo.co"]
    )
    admin_password: str = Field(
        ...,
        min_length=8,
        description="Contrasena del administrador (minimo 8 caracteres).",
        examples=["Secure123!"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "slug": "ikbo",
                "display_name": "IKBO SAS",
                "email_domain": "ikbo.co",
                "admin_email": "admin@ikbo.co",
                "admin_password": "Secure123!",
            }
        }
    }


class TenantResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    email_domain: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}
