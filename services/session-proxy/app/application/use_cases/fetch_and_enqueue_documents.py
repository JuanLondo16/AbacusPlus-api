import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.domain.ports.services import ExternalClientPort
from app.domain.ports.queue import JobQueuePort
from app.application.dto.documents import DocumentsRangeRequest, EnqueueDownloadsResponse
from app.infrastructure.queue.batch_store import RedisBatchStore

logger = logging.getLogger(__name__)

DOWNLOAD_ZIP_FUNCTION = "download_zip"


class FetchAndEnqueueDocumentsUseCase:
    DOCUMENTS_PATH = "/Document/GetDocumentsPageToken"

    def __init__(
        self,
        external_client: ExternalClientPort,
        job_queue: JobQueuePort,
        base_url: str,
        login_url: str,
        batch_store: RedisBatchStore,
    ):
        self._client = external_client
        self._queue = job_queue
        self._base_url = base_url.rstrip("/")
        self._login_url = login_url
        self._batch_store = batch_store

    async def execute(self, request: DocumentsRangeRequest) -> EnqueueDownloadsResponse:
        batch_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        body = request.model_dump(exclude={"token"})
        documents_url = f"{self._base_url}{self.DOCUMENTS_PATH}"

        result = await self._client.login_and_request(
            login_url=self._login_url,
            credentials={"token": request.token},
            method="POST",
            url=documents_url,
            body=body,
        )

        raw_docs = result.get("body", [])
        if isinstance(raw_docs, dict):
            raw_docs = raw_docs.get("data", [])
        if not isinstance(raw_docs, list):
            raw_docs = []

        logger.info(
            "Documentos encontrados en rango %s→%s: %d",
            request.StartDate, request.EndDate, len(raw_docs),
        )

        job_ids = []
        for doc in raw_docs:
            track_id = doc.get("Id") or doc.get("id")
            if not track_id:
                continue
            doc_type_id = doc.get("DocumentTypeId") or doc.get("documentTypeId")
            if str(doc_type_id) == "96":
                logger.info("Documento ignorado (DocumentTypeId=96) — trackId: %s", track_id)
                continue
            job_id = await self._queue.enqueue(
                DOWNLOAD_ZIP_FUNCTION,
                track_id=track_id,
                token=request.token,
            )
            job_ids.append(job_id)
            logger.info("Job encolado para trackId: %s → %s", track_id, job_id)

        await self._batch_store.save(batch_id, job_ids, started_at)
        logger.info("Batch %s iniciado con %d jobs", batch_id, len(job_ids))

        return EnqueueDownloadsResponse(
            batch_id=batch_id,
            enqueued=len(job_ids),
            job_ids=job_ids,
            StartDate=request.StartDate,
            EndDate=request.EndDate,
            started_at=started_at.isoformat(),
        )
