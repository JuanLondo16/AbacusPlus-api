from typing import Optional, List
from datetime import date
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.document import Document
from app.domain.ports.repositories import DocumentRepositoryPort


class DocumentRepository(DocumentRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_document_number(self, document_number: str) -> Optional[Document]:
        return self.db.query(Document).filter(
            Document.document_number == document_number
        ).first()

    def get_by_id(self, document_id: int) -> Optional[Document]:
        return self.db.query(Document).filter(Document.id == document_id).first()

    def get_by_date_range(self, date_start: date, date_end: date) -> List[Document]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"get_by_date_range called with: date_start={date_start}, date_end={date_end}")
        return self.db.query(Document).filter(
            Document.date >= date_start,
            Document.date <= date_end
        ).all()

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document
