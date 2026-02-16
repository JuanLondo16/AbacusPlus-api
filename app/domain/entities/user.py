from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserEntity:
    username: str
    email: str
    hashed_password: str
    tenant_id: int
    full_name: Optional[str] = None
    is_active: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
