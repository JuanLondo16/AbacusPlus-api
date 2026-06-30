from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.document_tax import DocumentTax


class DocumentTaxRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: int) -> list[DocumentTax]:
        return (
            self.db.query(DocumentTax)
            .filter(DocumentTax.document_id == document_id)
            .order_by(DocumentTax.id)
            .all()
        )

    def get(self, document_id: int, document_tax_id: int) -> Optional[DocumentTax]:
        return (
            self.db.query(DocumentTax)
            .filter(
                DocumentTax.id == document_tax_id,
                DocumentTax.document_id == document_id,
            )
            .first()
        )

    def create(self, document_id: int, tax_id: int, value: float) -> DocumentTax:
        row = DocumentTax(document_id=document_id, tax_id=tax_id, value=value)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(
        self,
        document_id: int,
        document_tax_id: int,
        tax_id: Optional[int] = None,
        value: Optional[float] = None,
    ) -> Optional[DocumentTax]:
        row = self.get(document_id, document_tax_id)
        if row is None:
            return None
        if tax_id is not None:
            row.tax_id = tax_id
        if value is not None:
            row.value = value
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, document_id: int, document_tax_id: int) -> bool:
        row = self.get(document_id, document_tax_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True
