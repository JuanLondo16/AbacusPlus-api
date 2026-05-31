from typing import Optional

from sqlalchemy.orm import Session

from app.domain.ports.repositories import IssuerRepositoryPort
from app.infrastructure.persistence.models.issuer import Issuer


class IssuerRepository(IssuerRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_nit(self, nit: str) -> Optional[Issuer]:
        return self.db.query(Issuer).filter(Issuer.nit == nit).first()

    def create(self, issuer: Issuer) -> Issuer:
        self.db.add(issuer)
        self.db.commit()
        self.db.refresh(issuer)
        return issuer
