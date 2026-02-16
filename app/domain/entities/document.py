from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List


@dataclass
class DocumentDetailEntity:
    description: str
    concept_description_id: int
    quantity: float
    unit: str
    price: float
    subtotal: float
    tax_type: str
    tax_value: float
    total: float
    id: Optional[int] = None
    document_id: Optional[int] = None


@dataclass
class DocumentEntity:
    document_name: str
    document_number: str
    date: date
    hour: str
    currency: str
    document_type: str
    uuid: str
    issuer_name: str
    issuer_nit: str
    receiver_name: str
    receiver_nit: str
    subtotal: float
    total_taxes: float
    total: float
    status: str
    issuer_phone: Optional[str] = None
    issuer_email: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_email: Optional[str] = None
    id: Optional[int] = None
    register_at: Optional[datetime] = None
    details: List[DocumentDetailEntity] = field(default_factory=list)
