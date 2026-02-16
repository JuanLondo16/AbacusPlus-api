from typing import Optional
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.tax import Tax
from app.domain.ports.repositories import TaxRepositoryPort


class TaxRepository(TaxRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_receiver_and_name(self, receiver_nit: str, tax_name: str) -> Optional[Tax]:
        return self.db.query(Tax).filter(
            Tax.receiver_nit == receiver_nit,
            Tax.tax == tax_name
        ).first()

    def create(self, tax: Tax) -> Tax:
        self.db.add(tax)
        self.db.commit()
        self.db.refresh(tax)
        return tax
