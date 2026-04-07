from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class EnqueueBatchResponse(BaseModel):
    queued: int
    files: List[str]


class ProcessingLogResponse(BaseModel):
    id: int
    filename: str
    xml_filename: Optional[str] = None
    status: str
    document_id: Optional[int] = None
    document_number: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: datetime

    model_config = {"from_attributes": True}
