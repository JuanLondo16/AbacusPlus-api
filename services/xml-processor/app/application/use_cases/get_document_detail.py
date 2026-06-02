from app.domain.exceptions.base import EntityNotFoundException
from app.domain.ports.repositories import DocumentRepositoryPort


class GetDocumentDetailUseCase:
    """Devuelve el documento completo con todas sus líneas de detalle enriquecidas."""

    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_id: int):
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise EntityNotFoundException("Document", str(document_id))
        return document
