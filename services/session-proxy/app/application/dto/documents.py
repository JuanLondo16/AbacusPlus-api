from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    batch_id: str = Field(..., description="Identificador único del batch. Úsalo en GET /dian/documents/batches/{batch_id} para consultar el estado.")
    enqueued: int = Field(..., description="Número de documentos encolados para descarga.")
    job_ids: List[str] = Field(..., description="IDs individuales de cada job ARQ.")
    StartDate: str
    EndDate: str
    started_at: str = Field(..., description="Fecha y hora de inicio del batch (ISO 8601 UTC).")


class DownloadJobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None


class BatchStatusResponse(BaseModel):
    batch_id: str = Field(..., description="Identificador del batch.")
    total: int = Field(..., description="Total de documentos encolados en el batch.")
    completed: int = Field(..., description="Documentos ya descargados y procesados.")
    pending: int = Field(..., description="Documentos pendientes.")
    percent_done: float = Field(..., description="Porcentaje de completado (0–100).")
    elapsed_seconds: float = Field(..., description="Segundos transcurridos desde el inicio.")
    total_time_seconds: Optional[float] = Field(None, description="Tiempo total de ejecución en segundos. Solo presente cuando el batch está completado.")
    is_done: bool = Field(..., description="True si todos los jobs del batch han finalizado.")
    started_at: str = Field(..., description="Fecha y hora de inicio (ISO 8601 UTC).")
