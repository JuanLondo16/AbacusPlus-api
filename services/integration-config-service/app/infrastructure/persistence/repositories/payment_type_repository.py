from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.payment_type import PaymentType


class PaymentTypeRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, payment_types: Iterable[dict]) -> int:
        synced = 0
        for item in payment_types:
            name = str(item["name"]).strip()
            model = self.db.query(PaymentType).filter(PaymentType.name == name).one_or_none()
            if model is None:
                model = PaymentType(name=name)
                self.db.add(model)

            model.type = item["type"]
            model.active = item.get("active", True)
            synced += 1

        self.db.commit()
        return synced

    def list(self, active: Optional[bool] = None) -> list[PaymentType]:
        query = self.db.query(PaymentType)
        if active is not None:
            query = query.filter(PaymentType.active.is_(active))
        return query.order_by(PaymentType.name.asc()).all()
