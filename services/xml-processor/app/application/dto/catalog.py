from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class CostCenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class PucAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    level: Optional[int] = None


class RetentionFuenteRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retention_concept: str
    taxpayer_type: str
    minimum_base_uvt: Optional[float] = None
    minimum_base_pesos: Optional[float] = None
    rate_percentage: float


class RetentionIcaRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    municipality_code: str
    municipality_name: Optional[str] = None
    percentage: float
