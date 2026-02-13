from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime,date

class DocumentBase(BaseModel):
    document_name: str = Field(..., max_length=255)
    document_number: str = Field(..., max_length=50)
    date: date
    hour: str = Field(..., max_length=20)
    currency: str = Field(..., max_length=3)
    document_type: str = Field(..., max_length=50)
    uuid: str = Field(..., max_length=255)
    issuer_name: str = Field(..., max_length=255)
    issuer_nit: str = Field(..., max_length=50)
    issuer_phone: Optional[str] = Field(None, max_length=20)
    issuer_email: Optional[str] = Field(None, max_length=255)
    receiver_name: str = Field(..., max_length=255)
    receiver_nit: str = Field(..., max_length=50)
    receiver_phone: Optional[str] = Field(None, max_length=20)
    receiver_email: Optional[str] = Field(None, max_length=255)
    subtotal: float
    total_taxes: float
    total: float
    register_at: datetime
    status: str = Field(..., max_length=50)

class DocumentDetailBase(BaseModel):
    description: str = Field(..., max_length=255)
    concept_description_id: int
    quantity: float
    unit: str = Field(..., max_length=20)
    price: float
    subtotal: float
    tax_type: str = Field(..., max_length=50)
    tax_value: float
    total: float

class DocumentDetail(DocumentDetailBase):
    id: int
    document_id: int

    class Config:
        from_attributes = True
        orm_mode = True

class Document(DocumentBase):
    id: int
    details: List[DocumentDetail] = []

    class Config:
        from_attributes = True
        orm_mode = True

class DocumentWithDetail(BaseModel):
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
    issuer_phone: Optional[str]
    issuer_email: Optional[str]
    receiver_name: str
    receiver_nit: str
    receiver_phone: Optional[str]
    receiver_email: Optional[str]
    subtotal: float
    total_taxes: float
    total: float
    register_at: datetime
    status: str
    details: List[DocumentDetail]

    class Config:
        from_attributes = True
        orm_mode = True