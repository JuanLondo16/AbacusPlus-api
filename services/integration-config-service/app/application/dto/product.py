from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProductResponse(BaseModel):
    id: int = Field(..., description="ID local del producto.", examples=[1])
    code: str = Field(..., description="Codigo del producto.", examples=["P-001"])
    type: str = Field(..., description="Tipo: 'product' o 'service'.", examples=["product"])
    description: str = Field(..., description="Descripcion del producto o servicio.", examples=["Licencia de software anual"])
    active: bool = Field(..., description="Estado del producto.", examples=[True])
    synced_at: datetime = Field(..., description="Fecha de sincronizacion local.")
    raw_payload: Dict[str, Any] = Field(..., description="Datos originales usados para crear/actualizar el producto.")

    model_config = {"from_attributes": True}


class ImportProductsResponse(BaseModel):
    imported: int = Field(..., description="Cantidad de filas creadas o actualizadas.", examples=[5])
    products: List[ProductResponse] = Field(..., description="Productos almacenados despues de la importacion.")
