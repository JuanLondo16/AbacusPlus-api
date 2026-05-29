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

    def get_by_date_range(self, date_start: date, date_end: date, status: Optional[int] = None) -> List[Document]:
        q = self.db.query(Document).filter(
            Document.date >= date_start,
            Document.date <= date_end,
        )
        if status is not None:
            q = q.filter(Document.status == status)
        return q.all()

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_status(self, document_id: int, new_status: str) -> Optional[Document]:
        doc = self.get_by_id(document_id)
        if doc is None:
            return None
        doc.status = new_status
        self.db.commit()
        self.db.refresh(doc)
        return doc
