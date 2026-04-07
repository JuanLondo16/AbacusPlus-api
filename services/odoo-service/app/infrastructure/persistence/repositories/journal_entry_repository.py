import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.journal_entry import HistoricalJournalEntry, HistoricalJournalEntryLine

logger = logging.getLogger(__name__)


class JournalEntryRepository:

    def __init__(self, db: Session):
        self._db = db

    def upsert_entry(
        self,
        move_data: dict,
        lines_data: List[dict],
        partner_map: Dict[int, dict],
        account_map: Dict[int, dict],
        analytic_map: Dict[int, dict],
        batch_id: str,
    ) -> Tuple[HistoricalJournalEntry, bool]:
        """
        Inserta o actualiza un asiento contable y sus líneas.
        Retorna (entry, is_new).
        """
        source_id: int = move_data["id"]
        existing = self._db.query(HistoricalJournalEntry).filter_by(source_id=source_id).first()
        is_new = existing is None

        partner_odoo_id = move_data["partner_id"][0] if move_data.get("partner_id") else None
        partner_info = partner_map.get(partner_odoo_id, {}) if partner_odoo_id else {}

        fields = {
            "source_id": source_id,
            "name": move_data.get("name") or None,
            "date": move_data.get("date") or None,
            "ref": move_data.get("ref") or None,
            "move_type": move_data.get("move_type") or None,
            "state": move_data.get("state") or None,
            "journal_id": move_data["journal_id"][0] if move_data.get("journal_id") else None,
            "journal_name": move_data["journal_id"][1] if move_data.get("journal_id") else None,
            "partner_id": partner_odoo_id,
            "partner_name": move_data["partner_id"][1] if move_data.get("partner_id") else None,
            "partner_vat": partner_info.get("vat") or None,
            "currency_name": move_data["currency_id"][1] if move_data.get("currency_id") else None,
            "amount_untaxed": float(move_data.get("amount_untaxed") or 0),
            "amount_tax": float(move_data.get("amount_tax") or 0),
            "amount_total": float(move_data.get("amount_total") or 0),
            "narration": move_data.get("narration") or None,
            "batch_id": batch_id,
            "extracted_at": datetime.utcnow(),
        }

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            # Elimina líneas anteriores para recrearlas
            self._db.query(HistoricalJournalEntryLine).filter_by(move_id=existing.id).delete()
            entry = existing
        else:
            entry = HistoricalJournalEntry(**fields)
            self._db.add(entry)
            self._db.flush()

        for ln in lines_data:
            if not ln.get("account_id"):
                continue  # Líneas de sección/nota sin cuenta contable

            account_odoo_id = ln["account_id"][0]
            account_info = account_map.get(account_odoo_id, {})

            # Centro de costo: analytic_distribution = {"<id>" o "<id1,id2>": porcentaje, ...}
            # En Odoo 17 las claves pueden ser compuestas ("11,14") al cruzar planes analíticos.
            cost_center = None
            if ln.get("analytic_distribution"):
                names = []
                for key in ln["analytic_distribution"].keys():
                    for part in key.split(","):
                        part = part.strip()
                        if part.isdigit():
                            analytic_info = analytic_map.get(int(part), {})
                            if analytic_info.get("name"):
                                names.append(analytic_info["name"])
                if names:
                    cost_center = ", ".join(dict.fromkeys(names))  # deduplica manteniendo orden

            line = HistoricalJournalEntryLine(
                source_id=ln["id"],
                move_id=entry.id,
                source_move_id=ln["move_id"][0] if ln.get("move_id") else None,
                sequence=ln.get("sequence") or 0,
                account_code=account_info.get("code") or None,
                account_name=account_info.get("name") or None,
                partner_name=ln["partner_id"][1] if ln.get("partner_id") else None,
                name=ln.get("name") or None,
                debit=float(ln.get("debit") or 0),
                credit=float(ln.get("credit") or 0),
                amount_currency=float(ln.get("amount_currency") or 0),
                cost_center=cost_center,
                date_maturity=ln.get("date_maturity") or None,
                extracted_at=datetime.utcnow(),
            )
            self._db.add(line)

        self._db.commit()
        self._db.refresh(entry)
        return entry, is_new

    def get_by_id(self, entry_id: int) -> Optional[HistoricalJournalEntry]:
        return (
            self._db.query(HistoricalJournalEntry)
            .filter(HistoricalJournalEntry.id == entry_id)
            .first()
        )

    def get_by_source_id(self, source_id: int) -> Optional[HistoricalJournalEntry]:
        return (
            self._db.query(HistoricalJournalEntry)
            .filter(HistoricalJournalEntry.source_id == source_id)
            .first()
        )

    def get_all(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        move_type: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[HistoricalJournalEntry]:
        query = self._db.query(HistoricalJournalEntry)
        if date_from:
            query = query.filter(HistoricalJournalEntry.date >= date_from)
        if date_to:
            query = query.filter(HistoricalJournalEntry.date <= date_to)
        if move_type:
            query = query.filter(HistoricalJournalEntry.move_type == move_type)
        if state:
            query = query.filter(HistoricalJournalEntry.state == state)
        return query.order_by(HistoricalJournalEntry.date.desc(), HistoricalJournalEntry.id.desc()).all()
