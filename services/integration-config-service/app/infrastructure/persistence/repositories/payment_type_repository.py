from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.payment_type import PaymentType


class PaymentTypeRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, payment_types: Iterable[dict], deactivate_missing: bool = False) -> int:
        items = list(payment_types)
        incoming_ids = [item["id"] for item in items if item.get("id") is not None]

        if deactivate_missing and incoming_ids:
            self.db.query(PaymentType).filter(PaymentType.id.notin_(incoming_ids)).delete(
                synchronize_session=False
            )

        synced = 0
        for item in items:
            siigo_id = item.get("id")
            name = str(item["name"]).strip()

            model = self.db.query(PaymentType).filter(PaymentType.id == siigo_id).one_or_none()
            if model is None:
                model = PaymentType(id=siigo_id)
                self.db.add(model)

            model.name = name
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
