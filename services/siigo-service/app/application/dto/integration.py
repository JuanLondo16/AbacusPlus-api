from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CredentialUpsertRequest(BaseModel):
    provider: str = Field("siigo", description="Proveedor de integracion.", examples=["siigo"])
    account_key: str = Field(
        "default",
        description="Llave interna de la empresa/cuenta conectada.",
        examples=["empresa-principal"],
    )
    username: str = Field(
        ..., description="Usuario API entregado por SIIGO.", examples=["api@empresa.com"]
    )
    access_key: str = Field(
        ..., description="Access key API entregada por SIIGO.", examples=["1234567890"]
    )
    base_url: HttpUrl = Field(
        "https://api.siigo.com",
        description="URL base del API de SIIGO.",
        examples=["https://api.siigo.com"],
    )
    partner_id: Optional[str] = Field(
        None, description="Partner-Id requerido por SIIGO cuando aplique.", examples=["abacusplus"]
    )
    chart_accounts_path: Optional[str] = Field(
        None,
        description="Ruta configurable para consultar el plan de cuentas si SIIGO la habilita para la cuenta.",
        examples=["/v1/accounts"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "provider": "siigo",
                "account_key": "empresa-principal",
                "username": "api@empresa.com",
                "access_key": "1234567890",
                "base_url": "https://api.siigo.com",
                "partner_id": "abacusplus",
                "chart_accounts_path": "/v1/accounts",
            }
        }
    }


class CredentialResponse(BaseModel):
    id: int = Field(..., description="ID local de la credencial.", examples=[1])
    provider: str = Field(..., description="Proveedor de integracion.", examples=["siigo"])
    account_key: str = Field(
        ...,
        description="Llave interna de la empresa/cuenta conectada.",
        examples=["empresa-principal"],
    )
    username: Optional[str] = Field(
        None, description="Usuario API registrado.", examples=["api@empresa.com"]
    )
    base_url: str = Field(
        ..., description="URL base usada por el conector.", examples=["https://api.siigo.com"]
    )
    partner_id: Optional[str] = Field(
        None, description="Partner-Id registrado.", examples=["abacusplus"]
    )
    expires_at: Optional[datetime] = Field(
        None, description="Fecha de expiracion del token JWT actual."
    )
    active: bool = Field(..., description="Indica si la credencial esta activa.", examples=[True])

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token_saved: bool = Field(
        ..., description="Indica si se guardo el access_token recibido.", examples=[True]
    )
    token_type: str = Field(
        ..., description="Tipo de token retornado por SIIGO.", examples=["Bearer"]
    )
    expires_at: datetime = Field(..., description="Fecha local calculada de expiracion del token.")
