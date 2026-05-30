from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class RuleMatchAttempt:
    document_id: int
    match_level: str  # HIT | PARTIAL | MISS
    confidence_at_match: float
    llm_used_context: bool
    rule_id: Optional[int] = None
    match_key_type: Optional[str] = None
    final_approved: Optional[bool] = None
    suggested_payload: Dict = field(default_factory=dict)
    id: Optional[int] = None
    created_at: Optional[datetime] = None
