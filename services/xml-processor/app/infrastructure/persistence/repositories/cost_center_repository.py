from typing import List
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.cost_center import CostCenter


class CostCenterRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> List[CostCenter]:
        return (
            self._db.query(CostCenter)
            .filter(CostCenter.is_active.is_(True))
            .order_by(CostCenter.code)
            .all()
        )
