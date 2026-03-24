from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class ChunkEntity:
    source_type: str
    content: str
    source_id: Optional[int] = None
    embedding: Optional[List[float]] = field(default=None)
    id: Optional[int] = None
    created_at: Optional[datetime] = None
