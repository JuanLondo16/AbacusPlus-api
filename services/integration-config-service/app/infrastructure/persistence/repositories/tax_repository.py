from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.tax import Tax


class TaxRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, taxes: Iterable[dict]) -> int:
        synced = 0
        for item in taxes:
            name = str(item["name"]).strip()
            model = self.db.query(Tax).filter(Tax.name == name).one_or_none()
            if model is None:
                model = Tax(name=name)
                self.db.add(model)

            model.type = item["type"]
            model.percentage = Decimal(str(item.get("percentage", 0)))
            model.active = item.get("active", True)
            synced += 1

        self.db.commit()
        return synced

    def list(self, active: Optional[bool] = None) -> list[Tax]:
        query = self.db.query(Tax)
        if active is not None:
            query = query.filter(Tax.active.is_(active))
        return query.order_by(Tax.name.asc()).all()
