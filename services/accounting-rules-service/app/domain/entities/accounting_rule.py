from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AccountingRule:
    match_key_type: str  # nit_semantic | nit_only | keyword_only
    suggested_debit_account: str
    suggested_credit_account: str
    confidence_score: float
    issuer_nit: Optional[str] = None
    description_embedding: Optional[list[float]] = field(default=None)
    ciiu_code: Optional[str] = None  # reservado para uso futuro
    item_keywords: Optional[list[str]] = field(default=None)
    suggested_tax_accounts: dict = field(default_factory=dict)
    suggested_cost_center: Optional[str] = None
    approval_count: int = 0
    edit_count: int = 0
    last_approved_at: Optional[datetime] = None
    is_active: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
