import logging

from app.application.dto.accounting import (
    GenerateAccountingRequest,
    RecalculateAccountingBatchRequest,
    RecalculateAccountingBatchResponse,
    RecalculateAccountingItemResult,
)
from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase
from app.infrastructure.clients.document_client import DocumentClient

logger = logging.getLogger(__name__)


class RecalculateAccountingBatchUseCase:
    """Recalcula la causación contable de todos los documentos en un rango de fechas."""

    def __init__(
        self,
        document_client: DocumentClient,
        generate_use_case: GenerateAccountingEntryUseCase,
    ):
        self._doc_client = document_client
        self._generate = generate_use_case

    async def execute(
        self, request: RecalculateAccountingBatchRequest
    ) -> RecalculateAccountingBatchResponse:
        documents = await self._doc_client.list_by_date_range(
            dateini=request.dateini,
            datefin=request.datefin,
            status_filter=request.status_filter,
        )
        logger.info(
            "Recálculo batch: %d documentos entre %s y %s (status=%s)",
            len(documents), request.dateini, request.datefin, request.status_filter,
        )

        results: list[RecalculateAccountingItemResult] = []
        generated = 0
        failed = 0

        for doc in documents:
            document_id = doc.get("id")
            document_number = doc.get("document_number")
            try:
                entry = await self._generate.execute(
                    GenerateAccountingRequest(
                        document_id=document_id,
                        top_k=request.top_k,
                        model=request.model,
                    )
                )
                if entry.status == "generated":
                    generated += 1
                else:
                    failed += 1
                results.append(
                    RecalculateAccountingItemResult(
                        document_id=document_id,
                        document_number=document_number,
                        status=entry.status,
                        accounting_entry_id=entry.id,
                        error_message=entry.error_message,
                    )
                )
            except Exception as e:
                failed += 1
                logger.error("Fallo recalculando doc_id=%s: %s", document_id, e)
                results.append(
                    RecalculateAccountingItemResult(
                        document_id=document_id,
                        document_number=document_number,
                        status="error",
                        accounting_entry_id=None,
                        error_message=str(e),
                    )
                )

        return RecalculateAccountingBatchResponse(
            dateini=request.dateini,
            datefin=request.datefin,
            total=len(documents),
            documents_read=len(documents),
            generated=generated,
            failed=failed,
            results=results,
        )
