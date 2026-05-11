from typing import List
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.puc import PucAccount


class PucRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> List[PucAccount]:
        return (
            self._db.query(PucAccount)
            .filter(PucAccount.is_active.is_(True))
            .order_by(PucAccount.code)
            .all()
        )
