from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CostCenterResponse(BaseModel):
    id: int = Field(..., description="ID local del centro de costo.", examples=[1])
    external_id: Optional[str] = Field(None, description="ID externo en el proveedor.", examples=["13222"])
    code: str = Field(..., description="Codigo del centro de costo.", examples=["1112"])
    name: str = Field(..., description="Nombre del centro de costo.", examples=["Administracion"])
    active: bool = Field(..., description="Estado del centro de costo.", examples=[True])
    synced_at: datetime = Field(..., description="Fecha de sincronizacion local.")
    raw_payload: Dict[str, Any] = Field(..., description="Datos originales usados para crear/actualizar el centro.")

    model_config = {"from_attributes": True}


class ImportCostCentersResponse(BaseModel):
    imported: int = Field(..., description="Cantidad de filas creadas o actualizadas.", examples=[8])
    cost_centers: List[CostCenterResponse] = Field(..., description="Centros almacenados despues de la importacion.")
