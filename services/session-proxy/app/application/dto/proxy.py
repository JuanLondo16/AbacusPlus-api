from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class ProxyRequest(BaseModel):
    token: str = Field(..., description="Token de autenticación DIAN")
    method: str = Field(..., description="Método HTTP: GET, POST, PUT, DELETE, PATCH")
    path: str = Field(..., description="Ruta relativa al EXTERNAL_BASE_URL, ej: /api/facturas")
    body: Optional[Dict[str, Any]] = Field(default=None)
    params: Optional[Dict[str, Any]] = Field(default=None)


class ProxyResponse(BaseModel):
    status_code: int
    body: Any
    headers: Dict[str, str] = Field(default_factory=dict)
    request_body: Optional[Dict[str, Any]] = Field(default=None)
