from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class SessionEntity:
    session_id: str
    cookies: Dict[str, str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)
