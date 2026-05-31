import logging

from fastapi import HTTPException, status

from app.application.dto.accounting import (
    GenerateAccountingRequest,
    RecalculateAccountingDocumentRequest,
    RecalculateAccountingItemResult,
)
from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase
from app.infrastructure.clients.document_client import DocumentClient

logger = logging.getLogger(__name__)


class RecalculateAccountingDocumentUseCase:
    """Recalcula la causación contable de un documento identificado por su ID."""

    def __init__(
        self,
        document_client: DocumentClient,
        generate_use_case: GenerateAccountingEntryUseCase,
    ):
        self._doc_client = document_client
        self._generate = generate_use_case

    async def execute(
        self, request: RecalculateAccountingDocumentRequest
    ) -> RecalculateAccountingItemResult:
        document = await self._doc_client.get_document(request.document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Documento {request.document_id} no encontrado en xml-processor.",
            )

        document_number = document.get("document_number")

        entry = await self._generate.execute(
            GenerateAccountingRequest(
                document_id=request.document_id,
                top_k=request.top_k,
                model=request.model,
            )
        )

        return RecalculateAccountingItemResult(
            document_id=request.document_id,
            document_number=document_number,
            status=entry.status,
            accounting_entry_id=entry.id,
            error_message=entry.error_message,
        )
