from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TaxResponse(BaseModel):
    id: int = Field(..., description="ID local del impuesto.", examples=[1])
    name: str = Field(..., description="Nombre del impuesto.", examples=["IVA 19%"])
    type: str = Field(..., description="Tipo de impuesto.", examples=["IVA"])
    percentage: Decimal = Field(..., description="Porcentaje del impuesto.", examples=["19.0000"])
    active: bool = Field(..., description="Estado del impuesto.", examples=[True])
    created_at: datetime = Field(..., description="Fecha de creacion.")
    updated_at: datetime = Field(..., description="Fecha de ultima actualizacion.")

    model_config = {"from_attributes": True}


class ImportTaxesResponse(BaseModel):
    imported: int = Field(
        ..., description="Cantidad de filas creadas o actualizadas.", examples=[5]
    )
    taxes: list[TaxResponse] = Field(
        ..., description="Impuestos almacenados despues de la importacion."
    )


class SyncSiigoTaxesRequest(BaseModel):
    account_key: str = Field(
        "default",
        description="Llave de cuenta en integration_credentials para el proveedor siigo.",
        examples=["default"],
    )

    model_config = {
        "json_schema_extra": {"example": {"account_key": "default"}}
    }
