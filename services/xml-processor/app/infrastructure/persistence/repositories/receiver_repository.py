from typing import Optional

from sqlalchemy.orm import Session

from app.domain.ports.repositories import ReceiverRepositoryPort
from app.infrastructure.persistence.models.receiver import Receiver


class ReceiverRepository(ReceiverRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_nit(self, nit: str) -> Optional[Receiver]:
        return self.db.query(Receiver).filter(Receiver.nit == nit).first()

    def get_all(self) -> list[Receiver]:
        return self.db.query(Receiver).all()

    def create(self, receiver: Receiver) -> Receiver:
        self.db.add(receiver)
        self.db.commit()
        self.db.refresh(receiver)
        return receiver
