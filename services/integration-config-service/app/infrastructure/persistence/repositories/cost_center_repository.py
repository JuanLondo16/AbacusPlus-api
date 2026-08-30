from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.cost_center import CostCenter


class CostCenterRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, cost_centers: Iterable[dict], deactivate_missing: bool = False) -> int:
        items = list(cost_centers)
        incoming_codes = [str(item["code"]) for item in items if item.get("code")]

        if deactivate_missing and incoming_codes:
            self.db.query(CostCenter).filter(CostCenter.code.notin_(incoming_codes)).delete(
                synchronize_session=False
            )

        synced = 0
        for cost_center in items:
            code = str(cost_center["code"])
            model = self.db.query(CostCenter).filter(CostCenter.code == code).one_or_none()
            if model is None:
                model = CostCenter(code=code)
                self.db.add(model)

            model.external_id = cost_center.get("external_id")
            model.name = cost_center["name"]
            model.active = cost_center.get("active", True)
            model.raw_payload = cost_center.get("raw_payload", {})
            synced += 1

        self.db.commit()
        return synced

    def list(self, active: Optional[bool] = None) -> list[CostCenter]:
        query = self.db.query(CostCenter)
        if active is not None:
            query = query.filter(CostCenter.active.is_(active))
        return query.order_by(CostCenter.code.asc()).all()
