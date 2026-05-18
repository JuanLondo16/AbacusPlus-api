from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChartAccountResponse(BaseModel):
    id: int = Field(..., description="ID local de la cuenta contable.", examples=[1])
    provider: str = Field(..., description="Proveedor origen o destino.", examples=["siigo"])
    account_key: str = Field(..., description="Cuenta/empresa conectada.", examples=["empresa-principal"])
    external_id: Optional[str] = Field(None, description="ID externo en el proveedor.", examples=["12345"])
    code: str = Field(..., description="Codigo contable.", examples=["510505"])
    name: str = Field(..., description="Nombre de la cuenta contable.", examples=["Gastos de personal"])
    account_type: Optional[str] = Field(None, description="Tipo/clase de cuenta.", examples=["Expense"])
    level: Optional[int] = Field(None, description="Nivel jerarquico de la cuenta.", examples=[4])
    parent_code: Optional[str] = Field(None, description="Codigo de la cuenta padre.", examples=["5105"])
    accepts_movements: Optional[bool] = Field(None, description="Indica si permite movimientos contables.", examples=[True])
    active: bool = Field(..., description="Estado de la cuenta.", examples=[True])
    synced_at: datetime = Field(..., description="Fecha de sincronizacion local.")
    raw_payload: Dict[str, Any] = Field(..., description="Datos originales usados para crear/actualizar la cuenta.")

    model_config = {"from_attributes": True}


class ImportChartAccountsResponse(BaseModel):
    provider: str = Field(..., description="Proveedor al que pertenece el plan importado.", examples=["siigo"])
    account_key: str = Field(..., description="Cuenta/empresa a la que pertenece el plan.", examples=["empresa-principal"])
    imported: int = Field(..., description="Cantidad de filas creadas o actualizadas.", examples=[42])
    accounts: List[ChartAccountResponse] = Field(..., description="Cuentas almacenadas despues de la importacion.")
