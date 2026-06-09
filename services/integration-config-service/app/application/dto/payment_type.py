from datetime import datetime

from pydantic import BaseModel, Field


class PaymentTypeResponse(BaseModel):
    id: int = Field(..., description="ID local del tipo de pago.", examples=[1])
    name: str = Field(..., description="Nombre del tipo de pago.", examples=["Transferencia bancaria"])
    type: str = Field(..., description="Categoria del tipo de pago.", examples=["electronico"])
    active: bool = Field(..., description="Estado del tipo de pago.", examples=[True])
    created_at: datetime = Field(..., description="Fecha de creacion.")
    updated_at: datetime = Field(..., description="Fecha de ultima actualizacion.")

    model_config = {"from_attributes": True}


class ImportPaymentTypesResponse(BaseModel):
    imported: int = Field(
        ..., description="Cantidad de filas creadas o actualizadas.", examples=[5]
    )
    payment_types: list[PaymentTypeResponse] = Field(
        ..., description="Tipos de pago almacenados despues de la importacion."
    )


