from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.chart_account import ChartAccount


class ChartAccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, provider: str, account_key: str, accounts: Iterable[dict]) -> int:
        synced = 0
        for account in accounts:
            code = str(account["code"])
            model = (
                self.db.query(ChartAccount)
                .filter(
                    ChartAccount.provider == provider,
                    ChartAccount.account_key == account_key,
                    ChartAccount.code == code,
                )
                .one_or_none()
            )
            if model is None:
                model = ChartAccount(provider=provider, account_key=account_key, code=code)
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

    def list(self, provider: str, account_key: str, active: Optional[bool] = None) -> List[ChartAccount]:
        query = self.db.query(ChartAccount).filter(
            ChartAccount.provider == provider,
            ChartAccount.account_key == account_key,
        )
        if active is not None:
            query = query.filter(ChartAccount.active.is_(active))
        return query.order_by(ChartAccount.code.asc()).all()
