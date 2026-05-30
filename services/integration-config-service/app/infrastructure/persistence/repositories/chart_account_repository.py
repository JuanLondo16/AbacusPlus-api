from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.chart_account import ChartAccount


class ChartAccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def delete_all(self) -> None:
        self.db.query(ChartAccount).delete()
        self.db.commit()

    def upsert_many(self, accounts: Iterable[dict]) -> int:
        synced = 0
        for account in accounts:
            code = str(account["code"])
            model = (
                self.db.query(ChartAccount)
                .filter(ChartAccount.code == code)
                .one_or_none()
            )
            if model is None:
                model = ChartAccount(code=code)
                self.db.add(model)

            model.external_id = account.get("external_id")
            model.name = account["name"]
            model.account_type = account.get("account_type")
            model.level = account.get("level")
            model.parent_code = account.get("parent_code")
            model.accepts_movements = account.get("accepts_movements")
            model.active = account.get("active", True)
            model.raw_payload = account.get("raw_payload", {})
            synced += 1

        self.db.commit()
        return synced

    def set_accepts_movements(self, movements: Dict[str, bool]) -> None:
        true_codes = [c for c, v in movements.items() if v]
        false_codes = [c for c, v in movements.items() if not v]
        if true_codes:
            self.db.query(ChartAccount).filter(ChartAccount.code.in_(true_codes)).update(
                {"accepts_movements": True}, synchronize_session=False
            )
        if false_codes:
            self.db.query(ChartAccount).filter(ChartAccount.code.in_(false_codes)).update(
                {"accepts_movements": False}, synchronize_session=False
            )
        self.db.commit()

    def list(self, active: Optional[bool] = None) -> List[ChartAccount]:
        query = self.db.query(ChartAccount)
        if active is not None:
            query = query.filter(ChartAccount.active.is_(active))
        return query.order_by(ChartAccount.code.asc()).all()
