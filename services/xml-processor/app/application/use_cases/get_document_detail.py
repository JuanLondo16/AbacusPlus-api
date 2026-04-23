from typing import Optional

from app.domain.ports.repositories import DocumentRepositoryPort
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.clients.llm_client import LlmClient


class GetDocumentDetailWithAccountingUseCase:
    """
    Devuelve el detalle completo de un documento:
    - xml_reading: cabecera + líneas del XML (desde la BD local)
    - accounting: último asiento contable generado (desde llm-service, best-effort)
    """

    def __init__(self, document_repo: DocumentRepositoryPort, llm_client: LlmClient):
        self.document_repo = document_repo
        self.llm_client = llm_client

    async def execute(self, document_id: int) -> dict:
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise EntityNotFoundException("Document", str(document_id))

        accounting = await self.llm_client.get_accounting_entry(document_id)

        return {"document": document, "accounting": accounting}
