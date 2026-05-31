import logging

from app.domain.exceptions.base import EntityNotFoundException
from app.domain.ports.repositories import DocumentRepositoryPort
from app.domain.value_objects.document_status import DocumentStatus

logger = logging.getLogger(__name__)


class ApproveDocumentUseCase:
    def __init__(
        self,
        document_repo: DocumentRepositoryPort,
        llm_client=None,
        accounting_rules_client=None,
    ):
        self.document_repo = document_repo
        self._llm_client = llm_client
        self._accounting_rules_client = accounting_rules_client

    async def execute(self, document_id: int):
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise EntityNotFoundException(f"Document {document_id} not found")
        if doc.status != DocumentStatus.CAUSADO:
            raise ValueError("Document must be in 'Causado' status (200) to approve")

        approved_doc = self.document_repo.update_status(document_id, DocumentStatus.APROBADO)

        # Best-effort: notificar al accounting-rules-service con el asiento aprobado
        await self._notify_rules_service(doc, document_id)

        return approved_doc

    async def _notify_rules_service(self, doc, document_id: int):
        if self._llm_client is None or self._accounting_rules_client is None:
            return
        try:
            entry = await self._llm_client.get_accounting_entry(document_id)
            if not entry:
                logger.info(
                    "Sin asiento en llm-service para doc=%s, skip notificación", document_id
                )
                return

            items = [
                {"description": d.description, "subtotal": d.subtotal} for d in (doc.details or [])
            ]
            approved_lines = [
                {
                    "cuenta": line.get("cuenta", ""),
                    "nombre": line.get("nombre"),
                    "debito": line.get("debito", 0.0),
                    "credito": line.get("credito", 0.0),
                    "tercero": line.get("tercero"),
                    "centro_costo": line.get("centro_costo"),
                    "descripcion": line.get("descripcion"),
                }
                for line in entry.get("lines", [])
            ]

            payload = {
                "document_id": document_id,
                "issuer_nit": doc.issuer_nit,
                "items": items,
                "approved_lines": approved_lines,
            }
            await self._accounting_rules_client.notify_approval(payload)
        except Exception as exc:
            logger.warning(
                "Error preparando notificación de aprobación para doc=%s: %s", document_id, exc
            )


class UnapproveDocumentUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_id: int):
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise EntityNotFoundException(f"Document {document_id} not found")
        if doc.status != DocumentStatus.APROBADO:
            raise ValueError("Document must be in 'Aprobado' status (300) to unapprove")
        return self.document_repo.update_status(document_id, DocumentStatus.CAUSADO)
