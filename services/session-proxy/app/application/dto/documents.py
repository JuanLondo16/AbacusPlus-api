from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DocumentsRangeRequest(BaseModel):
    token: str
    StartDate: str
    EndDate: str
    draw: int = 1
    start: int = 0
    length: int = 100
    DocumentKey: str = ""
    SerieAndNumber: str = ""
    SenderCode: str = ""
    ReceiverCode: str = ""
    DocumentTypeId: str = "00"
    Status: str = "0"
    IsNextPage: bool = False
    FilterType: str = "3"
    blockIndex: int = 0
    RadianStatus: str = "0"


class EnqueueDownloadsResponse(BaseModel):
    enqueued: int
    job_ids: List[str]
    StartDate: str
    EndDate: str


class DownloadJobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
