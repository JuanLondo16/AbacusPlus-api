from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.cost_center import CostCenter


class CostCenterRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, provider: str, account_key: str, cost_centers: Iterable[dict]) -> int:
        synced = 0
        for cost_center in cost_centers:
            code = str(cost_center["code"])
            model = (
                self.db.query(CostCenter)
                .filter(
                    CostCenter.provider == provider,
                    CostCenter.account_key == account_key,
                    CostCenter.code == code,
                )
                .one_or_none()
            )
            if model is None:
                model = CostCenter(provider=provider, account_key=account_key, code=code)
                self.db.add(model)

            model.external_id = cost_center.get("external_id")
            model.name = cost_center["name"]
            model.active = cost_center.get("active", True)
            model.raw_payload = cost_center.get("raw_payload", {})
            synced += 1

        self.db.commit()
        return synced

    def list(
        self, provider: str, account_key: str, active: Optional[bool] = None
    ) -> list[CostCenter]:
        query = self.db.query(CostCenter).filter(
            CostCenter.provider == provider,
            CostCenter.account_key == account_key,
        )
        if active is not None:
            query = query.filter(CostCenter.active.is_(active))
        return query.order_by(CostCenter.code.asc()).all()
