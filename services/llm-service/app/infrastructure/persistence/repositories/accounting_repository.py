from typing import List, Optional
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.accounting_entry import AccountingEntry, AccountingEntryLine


class AccountingRepository:
    def __init__(self, db: Session):
        self._db = db

    def create(self, entry: AccountingEntry, lines_data: List[dict]) -> AccountingEntry:
        """
        Persiste el asiento contable y crea cada línea como registro independiente.
        lines_data es una lista de dicts con claves: cuenta, nombre, debito, credito,
        tercero (opcional), centro_costo (opcional), descripcion (opcional).
        """
        self._db.add(entry)
        self._db.flush()  # obtiene entry.id antes del commit

        for line in lines_data:
            self._db.add(AccountingEntryLine(
                entry_id=entry.id,
                cuenta=line.get("cuenta", ""),
                nombre=line.get("nombre", ""),
                debito=float(line.get("debito") or 0),
                credito=float(line.get("credito") or 0),
                tercero=line.get("tercero") or None,
                centro_costo=line.get("centro_costo") or None,
                descripcion=line.get("descripcion") or None,
            ))

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
