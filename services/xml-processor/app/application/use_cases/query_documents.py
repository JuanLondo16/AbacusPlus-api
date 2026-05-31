from datetime import date
from typing import Optional

from app.domain.exceptions.base import EntityNotFoundException, ValidationException
from app.domain.ports.repositories import DocumentRepositoryPort


class GetDocumentsByDateRangeUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, date_start: date, date_end: date, status: Optional[str] = None) -> list:
        if date_end < date_start:
            raise ValidationException("End date cannot be before start date")
        return self.document_repo.get_by_date_range(date_start, date_end, status)


class GetDocumentByIdUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_id: int):
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise EntityNotFoundException("Document", str(document_id))
        return document
