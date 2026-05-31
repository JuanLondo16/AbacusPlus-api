from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChunkEntity:
    source_type: str
    content: str
    source_id: Optional[int] = None
    embedding: Optional[list[float]] = field(default=None)
    id: Optional[int] = None
    created_at: Optional[datetime] = None
