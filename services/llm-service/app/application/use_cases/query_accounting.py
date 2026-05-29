import logging

from fastapi import HTTPException

from app.application.dto.accounting import AccountingEntryResponse, DocumentWithAccountingResponse
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
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        entry = self._accounting_repo.get_latest_by_document_id(document_id)

        accounting_entry = None
        if entry:
            codes = [line.cuenta for line in entry.lines if line.cuenta]
            chart_names = self._accounting_repo.get_chart_account_name_map(codes)

            lines_data = [
                {
                    "id": line.id,
                    "cuenta": line.cuenta,
                    "nombre": chart_names.get(line.cuenta, "") if line.cuenta else "",
                    "debito": float(line.debito),
                    "credito": float(line.credito),
                    "tercero": line.tercero,
                    "centro_costo": line.centro_costo,
                    "descripcion": line.descripcion,
                }
                for line in entry.lines
            ]
            entry_dict = {
                "id": entry.id,
                "system_prompt_id": entry.system_prompt_id,
                "lines": lines_data,
                "model_used": entry.model_used,
                "status": entry.status,
                "error_message": entry.error_message,
                "rag_context": entry.rag_context,
                "created_at": entry.created_at,
            }
            accounting_entry = AccountingEntryResponse.model_validate(entry_dict)

        return DocumentWithAccountingResponse(
            document=document,
            accounting_entry=accounting_entry,
        )
