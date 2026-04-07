from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    date_from: date = Field(
        ...,
        description="Fecha inicial del rango de extracción (YYYY-MM-DD).",
        examples=["2024-01-01"],
    )
    date_to: date = Field(
        ...,
        description="Fecha final del rango de extracción (YYYY-MM-DD).",
        examples=["2024-12-31"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {"date_from": "2024-01-01", "date_to": "2024-12-31"}
        }
    }


class SyncResponse(BaseModel):
    synced: int = Field(..., description="Total de asientos procesados desde Odoo.")
    created: int = Field(..., description="Asientos nuevos insertados en la base de datos.")
    updated: int = Field(..., description="Asientos existentes actualizados.")
    batch_id: str = Field(..., description="UUID del lote de sincronización.")
    date_from: str = Field(..., description="Fecha inicial consultada.")
    date_to: str = Field(..., description="Fecha final consultada.")
    errors: List[dict] = Field(default_factory=list, description="Errores por asiento, si los hay.")


class JournalEntryLineResponse(BaseModel):
    id: int
    source_id: int
    sequence: int
    account_code: Optional[str]
    account_name: Optional[str]
    partner_name: Optional[str]
    name: Optional[str]
    debit: float
    credit: float
    amount_currency: float
    cost_center: Optional[str]
    date_maturity: Optional[date]
    extracted_at: datetime

    model_config = {"from_attributes": True}


class JournalEntryResponse(BaseModel):
    id: int
    source_id: int
    name: Optional[str]
    date: Optional[date]
    ref: Optional[str]
    move_type: Optional[str]
    state: Optional[str]
    journal_id: Optional[int]
    journal_name: Optional[str]
    partner_id: Optional[int]
    partner_name: Optional[str]
    partner_vat: Optional[str]
    currency_name: Optional[str]
    amount_untaxed: float
    amount_tax: float
    amount_total: float
    narration: Optional[str]
    batch_id: Optional[str]
    extracted_at: datetime

    model_config = {"from_attributes": True}


class JournalEntryDetailResponse(JournalEntryResponse):
    lines: List[JournalEntryLineResponse] = Field(default_factory=list)
