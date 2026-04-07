from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.application.dto.batch import EnqueueBatchResponse, ProcessingLogResponse
from app.application.use_cases.process_downloads import ProcessDownloadsUseCase
from app.infrastructure.persistence.repositories.processing_log_repository import ProcessingLogRepository
from app.dependencies import get_process_downloads_use_case, get_processing_log_repo

router = APIRouter()


@router.post(
    "/batch/process-downloads",
    response_model=EnqueueBatchResponse,
    status_code=202,
    summary="Procesar descargas pendientes",
    description=(
        "Escanea la carpeta configurada en `DOWNLOADS_DIR` (por defecto `/app/downloads`), "
        "encola cada archivo `.zip` encontrado y retorna inmediatamente. "
        "El procesamiento ocurre en segundo plano: cada ZIP se descomprime, se parsea el XML "
        "DIAN, se guarda en la base de datos, se indexa en RAG y se solicita la generación "
        "del asiento contable al servicio LLM.\n\n"
        "Los archivos procesados se mueven a `downloads/processed/`. "
        "Los que generan error se mueven a `downloads/errors/`.\n\n"
        "**Idempotente:** si no hay ZIPs pendientes retorna `enqueued: 0` sin error."
    ),
    response_description="Cantidad de archivos encolados para procesamiento.",
)
async def process_downloads(
    use_case: ProcessDownloadsUseCase = Depends(get_process_downloads_use_case),
):
    return await use_case.execute()


@router.get(
    "/batch/logs",
    response_model=List[ProcessingLogResponse],
    summary="Historial de procesamiento batch",
    description=(
        "Retorna el historial de todos los archivos procesados por el worker batch, "
        "con su estado final y el resultado de la solicitud de asiento contable al LLM.\n\n"
        "**Estados posibles (`status`):**\n"
        "- `added` — documento procesado y guardado correctamente.\n"
        "- `duplicate` — el número de documento ya existía en la BD.\n"
        "- `error` — ocurrió un error durante el procesamiento.\n\n"
        "**Estados de causación (`accounting_status`):**\n"
        "- `triggered` — el LLM recibió la solicitud y respondió con éxito.\n"
        "- `error` — la solicitud al LLM falló (ver `accounting_error`).\n"
        "- `null` — no aplica (documento duplicado o con error de procesamiento)."
    ),
    response_description="Lista de registros de procesamiento, ordenados del más reciente al más antiguo.",
)
async def get_processing_logs(
    status: Optional[str] = Query(
        None,
        description="Filtrar por estado: `added`, `duplicate` o `error`.",
    ),
    log_repo: ProcessingLogRepository = Depends(get_processing_log_repo),
):
    return log_repo.get_all(status=status)
