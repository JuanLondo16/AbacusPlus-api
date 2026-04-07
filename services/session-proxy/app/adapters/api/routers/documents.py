from fastapi import APIRouter, Depends

from app.application.dto.documents import (
    DocumentsRangeRequest,
    EnqueueDownloadsResponse,
    DownloadJobStatus,
)
from app.application.use_cases.fetch_and_enqueue_documents import FetchAndEnqueueDocumentsUseCase
from app.application.use_cases.get_job_status import GetJobStatusUseCase
from app.dependencies import get_fetch_and_enqueue_use_case, get_job_status_use_case

router = APIRouter()


@router.post(
    "/dian/documents/enqueue",
    response_model=EnqueueDownloadsResponse,
    status_code=202,
    summary="Consulta documentos DIAN por rango de fechas y encola descarga de ZIPs",
)
async def enqueue_document_downloads(
    request: DocumentsRangeRequest,
    use_case: FetchAndEnqueueDocumentsUseCase = Depends(get_fetch_and_enqueue_use_case),
):
    return await use_case.execute(request)


@router.get(
    "/dian/documents/jobs/{job_id}",
    response_model=DownloadJobStatus,
    summary="Consulta el estado de un job de descarga de ZIP",
)
async def get_download_job_status(
    job_id: str,
    use_case: GetJobStatusUseCase = Depends(get_job_status_use_case),
):
    return await use_case.execute(job_id)
