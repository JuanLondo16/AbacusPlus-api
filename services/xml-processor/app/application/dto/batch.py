from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EnqueueBatchResponse(BaseModel):
    queued: int
    files: list[str]


class ProcessFileRequest(BaseModel):
    filename: str = Field(
        ..., description="Nombre del archivo ZIP en DOWNLOADS_DIR, ej: 'abc123.zip'."
    )
    job_id: str = Field(
        ...,
        description="ID del job ARQ que originó la descarga. Se usa para actualizar el estado en Redis.",
    )


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
