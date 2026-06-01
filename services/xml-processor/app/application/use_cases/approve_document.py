from app.domain.exceptions.base import EntityNotFoundException
from app.domain.ports.repositories import DocumentRepositoryPort
from app.domain.value_objects.document_status import DocumentStatus


class ApproveDocumentUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_id: int):
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise EntityNotFoundException(f"Document {document_id} not found")
        if doc.status != DocumentStatus.CAUSADO:
            raise ValueError("Document must be in 'Causado' status (200) to approve")
        return self.document_repo.update_status(document_id, DocumentStatus.APROBADO)


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
