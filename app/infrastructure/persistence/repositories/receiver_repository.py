from typing import Optional, List
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.receiver import Receiver
from app.domain.ports.repositories import ReceiverRepositoryPort


class ReceiverRepository(ReceiverRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_nit(self, nit: str) -> Optional[Receiver]:
        return self.db.query(Receiver).filter(Receiver.nit == nit).first()

    def get_all(self) -> List[Receiver]:
        return self.db.query(Receiver).all()

    def create(self, receiver: Receiver) -> Receiver:
        self.db.add(receiver)
        self.db.commit()
        self.db.refresh(receiver)
        return receiver
