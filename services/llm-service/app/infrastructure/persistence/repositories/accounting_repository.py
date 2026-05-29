from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.accounting_entry import AccountingEntry, AccountingEntryLine
from app.infrastructure.persistence.models.chart_account import IntegrationChartAccount


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

    def find_historical_by_issuer(
        self,
        issuer_nit: str,
        months_back: int = 12,
        limit: int = 50,
    ) -> List[dict]:
        """
        Devuelve hasta `limit` asientos generados del mismo emisor (por NIT exacto)
        dentro de los últimos `months_back` meses, ordenados del más reciente al más antiguo.
        Cada resultado incluye las líneas con cuenta, nombre, centro_costo y descripcion
        (sin valores monetarios — solo se usa para inferir distribución contable).
        """
        if not issuer_nit or not issuer_nit.strip():
            return []

        cutoff = datetime.utcnow() - timedelta(days=months_back * 30)

        entries = (
            self._db.query(AccountingEntry)
            .filter(
                AccountingEntry.status == "generated",
                AccountingEntry.issuer_nit == issuer_nit.strip(),
                AccountingEntry.created_at >= cutoff,
            )
            .order_by(AccountingEntry.created_at.desc())
            .limit(limit)
            .all()
        )

        results = []
        for entry in entries:
            lines = [
                {
                    "cuenta": str(line.cuenta),
                    "nombre": str(line.nombre),
                    "centro_costo": line.centro_costo,
                    "descripcion": line.descripcion,
                }
                for line in entry.lines
            ]
            results.append(
                {
                    "entry_id": entry.id,
                    "created_at": str(entry.created_at),
                    "lines": lines,
                }
            )
        return results

    def get_latest_by_document_id(self, document_id: int) -> Optional[AccountingEntry]:
        return (
            self._db.query(AccountingEntry)
            .filter(AccountingEntry.document_id == document_id)
            .order_by(AccountingEntry.created_at.desc())
            .first()
        )

    def get_chart_account_name_map(self, codes: List[str]) -> Dict[str, str]:
        if not codes:
            return {}
        rows = (
            self._db.query(IntegrationChartAccount)
            .filter(
                IntegrationChartAccount.code.in_(codes),
                IntegrationChartAccount.active == True,
            )
            .all()
        )
        return {row.code: row.name for row in rows}

    def link_to_document(self, document_id: int, entry_id: int) -> None:
        self._db.execute(
            text("UPDATE documents SET accounting_entry_id = :eid, status = 200 WHERE id = :did"),
            {"eid": entry_id, "did": document_id},
        )
        self._db.commit()

