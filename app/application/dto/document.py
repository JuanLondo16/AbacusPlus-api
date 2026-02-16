from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional, List


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    description: str
    concept_description_id: int
    quantity: float
    unit: str
    price: float
    subtotal: float
    tax_type: str
    tax_value: float
    total: float


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_name: str
    document_number: str
    date: date
    hour: str
    currency: str
    document_type: str
    uuid: str
    issuer_name: str
    issuer_nit: str
    issuer_phone: Optional[str] = None
    issuer_email: Optional[str] = None
    receiver_name: str
    receiver_nit: str
    receiver_phone: Optional[str] = None
    receiver_email: Optional[str] = None
    subtotal: float
    total_taxes: float
    total: float
    register_at: datetime
    status: str
    details: List[DocumentDetailResponse] = []


class ProcessXmlResponse(BaseModel):
    status: str
    data: dict
    document_id: int
    filename: str
