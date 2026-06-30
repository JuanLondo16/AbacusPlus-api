from typing import Optional

from pydantic import BaseModel, Field


class DocumentTaxResponse(BaseModel):
    id: int = Field(..., description="ID del registro de impuesto del documento.", examples=[1])
    document_id: int = Field(..., description="ID del documento al que pertenece.", examples=[10])
    tax_id: int = Field(
        ...,
        description="ID del impuesto en el catálogo local `integration_taxes`.",
        examples=[3],
    )
    value: float = Field(..., description="Valor del impuesto para el documento.", examples=[19000.0])

    model_config = {"from_attributes": True}


class DocumentTaxCreateRequest(BaseModel):
    tax_id: int = Field(
        ...,
        description="ID del impuesto en el catálogo local `integration_taxes`.",
        examples=[3],
    )
    value: float = Field(..., description="Valor del impuesto para el documento.", examples=[19000.0])

    model_config = {"json_schema_extra": {"example": {"tax_id": 3, "value": 19000.0}}}


class DocumentTaxUpdateRequest(BaseModel):
    tax_id: Optional[int] = Field(
        None,
        description="Nuevo ID de impuesto. Si se omite, no se modifica.",
        examples=[3],
    )
    value: Optional[float] = Field(
        None, description="Nuevo valor. Si se omite, no se modifica.", examples=[21000.0]
    )

    model_config = {"json_schema_extra": {"example": {"value": 21000.0}}}
