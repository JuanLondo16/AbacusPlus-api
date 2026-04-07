import logging
from typing import Optional

from app.application.dto.accounting import DocumentWithAccountingResponse, AccountingEntryResponse
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.persistence.repositories.accounting_repository import AccountingRepository

logger = logging.getLogger(__name__)


class QueryAccountingUseCase:
    def __init__(
        self,
        document_client: DocumentClient,
        accounting_repo: AccountingRepository,
    ):
        self._doc_client = document_client
        self._accounting_repo = accounting_repo

    async def execute(self, document_id: int) -> DocumentWithAccountingResponse:
        document = await self._doc_client.get_document(document_id)
        entry = self._accounting_repo.get_latest_by_document_id(document_id)

        return DocumentWithAccountingResponse(
            document=document,
            accounting_entry=AccountingEntryResponse.model_validate(entry) if entry else None,
        )
