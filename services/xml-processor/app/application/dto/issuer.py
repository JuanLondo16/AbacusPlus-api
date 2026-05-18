from typing import Optional

from pydantic import BaseModel, ConfigDict


class IssuerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nit: str
    dv: int
    phone: Optional[str] = None
    email: Optional[str] = None
    account_number: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    notes: Optional[str] = None
