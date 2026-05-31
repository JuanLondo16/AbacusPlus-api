from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionEntity:
    session_id: str
    cookies: dict[str, str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)
