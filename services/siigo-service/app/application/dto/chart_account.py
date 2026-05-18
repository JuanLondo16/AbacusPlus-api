from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SyncChartAccountsRequest(BaseModel):
    account_key: str = Field("default", description="Cuenta/empresa conectada a sincronizar.", examples=["empresa-principal"])
    page_size: int = Field(100, ge=1, le=500, description="Cantidad de registros por pagina.", examples=[100])
    path: Optional[str] = Field(
        None,
        description="Ruta SIIGO a consultar. Si no se envia, se usa la ruta guardada en la credencial o SIIGO_CHART_ACCOUNTS_PATH.",
        examples=["/v1/accounts"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {"account_key": "empresa-principal", "page_size": 100, "path": "/v1/accounts"}
        }
    }


class ChartAccountResponse(BaseModel):
    id: int = Field(..., description="ID local de la cuenta contable.", examples=[1])
    provider: str = Field(..., description="Proveedor origen.", examples=["siigo"])
    account_key: str = Field(..., description="Cuenta/empresa conectada.", examples=["empresa-principal"])
    external_id: Optional[str] = Field(None, description="ID externo en SIIGO cuando viene en la respuesta.", examples=["12345"])
    code: str = Field(..., description="Codigo contable.", examples=["510505"])
    name: str = Field(..., description="Nombre de la cuenta contable.", examples=["Gastos de personal"])
    account_type: Optional[str] = Field(None, description="Tipo/clase de cuenta si SIIGO lo retorna.", examples=["Expense"])
    level: Optional[int] = Field(None, description="Nivel jerarquico de la cuenta.", examples=[4])
    parent_code: Optional[str] = Field(None, description="Codigo de la cuenta padre.", examples=["5105"])
    accepts_movements: Optional[bool] = Field(None, description="Indica si permite movimientos contables.", examples=[True])
    active: bool = Field(..., description="Estado de la cuenta.", examples=[True])
    synced_at: datetime = Field(..., description="Fecha de sincronizacion local.")
    raw_payload: Dict[str, Any] = Field(..., description="Payload completo retornado por SIIGO para trazabilidad.")

    model_config = {"from_attributes": True}


class SyncChartAccountsResponse(BaseModel):
    synced: int = Field(..., description="Cantidad de cuentas creadas o actualizadas.", examples=[42])
    accounts: List[ChartAccountResponse] = Field(..., description="Cuentas actualmente almacenadas para la integracion.")
