from typing import List, Optional
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.accounting_entry import AccountingEntry


class AccountingRepository:
    def __init__(self, db: Session):
        self._db = db

    def create(self, entry: AccountingEntry) -> AccountingEntry:
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        return entry

    def get_by_document_id(self, document_id: int) -> List[AccountingEntry]:
        return (
            self._db.query(AccountingEntry)
            .filter(AccountingEntry.document_id == document_id)
            .order_by(AccountingEntry.created_at.desc())
            .all()
        )

    def get_latest_by_document_id(self, document_id: int) -> Optional[AccountingEntry]:
        return (
            self._db.query(AccountingEntry)
            .filter(AccountingEntry.document_id == document_id)
            .order_by(AccountingEntry.created_at.desc())
            .first()
        )
