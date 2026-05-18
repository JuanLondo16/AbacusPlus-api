import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.accounting_entry import AccountingEntry, AccountingEntryLine

logger = logging.getLogger(__name__)

_AMOUNT_TOLERANCE = 1.0  # tolerancia en COP para comparar totales


def _clean_nit(nit: str) -> Optional[str]:
    """Normaliza un NIT eliminando puntos, comas y guiones,
    e ignora el dígito de verificación (todo lo que va después del primer guión)."""
    if not nit:
        return None
    nit = nit.split("-")[0]
    return nit.replace(".", "").replace(",", "").replace("-", "").strip() or None


class AccountingEntryRepository:

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
    ) -> Tuple[AccountingEntry, bool]:
        """
        Inserta o actualiza un asiento contable y sus líneas.
        En actualizaciones preserva el document_id ya asociado.
        Retorna (entry, is_new).
        """
        source_id: int = move_data["id"]
        existing = self._db.query(AccountingEntry).filter_by(source_id=source_id).first()
        is_new = existing is None

        partner_odoo_id = move_data["partner_id"][0] if move_data.get("partner_id") else None
        partner_info = partner_map.get(partner_odoo_id, {}) if partner_odoo_id else {}

        fields = {
            "source_id": source_id,
            "source": "odoo",
            "name": move_data.get("name") or None,
            "date": move_data.get("date") or None,
            "ref": move_data.get("ref") or None,
            "move_type": move_data.get("move_type") or None,
            "state": move_data.get("state") or None,
            "journal_id": move_data["journal_id"][0] if move_data.get("journal_id") else None,
            "journal_name": move_data["journal_id"][1] if move_data.get("journal_id") else None,
            "partner_id": partner_odoo_id,
            "partner_name": move_data["partner_id"][1] if move_data.get("partner_id") else None,
            "partner_vat": _clean_nit(partner_info.get("vat") or ""),
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
            # document_id no está en fields → se preserva automáticamente
            self._db.query(AccountingEntryLine).filter_by(entry_id=existing.id).delete()
            entry = existing
        else:
            entry = AccountingEntry(**fields)
            self._db.add(entry)
            self._db.flush()

        for ln in lines_data:
            if not ln.get("account_id"):
                continue

            account_odoo_id = ln["account_id"][0]
            account_info = account_map.get(account_odoo_id, {})

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
                    cost_center = ", ".join(dict.fromkeys(names))

            line = AccountingEntryLine(
                source_id=ln["id"],
                entry_id=entry.id,
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

    def find_and_link_document(self, entry: AccountingEntry) -> Optional[int]:
        """
        Busca en la tabla documents un registro que coincida con el asiento por:
          - fecha exacta
          - issuer_nit igual al partner_vat del asiento
          - total dentro de ±1 COP
          - sin asociación previa (accounting_entry_id IS NULL)

        Si encuentra coincidencia actualiza accounting_entries.document_id
        y documents.accounting_entry_id en ambas tablas.
        Solo actúa si el asiento aún no tiene document_id.
        Retorna el document_id asociado o None.
        """
        if entry.document_id is not None:
            return entry.document_id
        nit = _clean_nit(entry.partner_vat or "")
        if not nit:
            logger.warning(
                "Match omitido — entry id=%s source_id=%s: partner_vat vacío o nulo (valor original: %r).",
                entry.id, entry.source_id, entry.partner_vat,
            )
            return None
        if not entry.date:
            logger.warning(
                "Match omitido — entry id=%s source_id=%s: fecha nula.",
                entry.id, entry.source_id,
            )
            return None

        row = self._db.execute(
            text(
                "SELECT id FROM documents "
                "WHERE date = :date "
                "  AND issuer_nit = :nit "
                "  AND ABS(total - :total) <= :tol "
                "  AND accounting_entry_id IS NULL "
                "ORDER BY id LIMIT 1"
            ),
            {
                "date": str(entry.date),
                "nit": nit,
                "total": float(entry.amount_total),
                "tol": _AMOUNT_TOLERANCE,
            },
        ).fetchone()

        if not row:
            self._log_match_failure(entry, nit)
            return None

        document_id = row[0]
        entry.document_id = document_id
        self._db.execute(
            text("UPDATE documents SET accounting_entry_id = :eid WHERE id = :did"),
            {"eid": entry.id, "did": document_id},
        )
        self._db.commit()
        self._db.refresh(entry)
        logger.info("Asiento source_id=%s asociado con document_id=%s", entry.source_id, document_id)
        return document_id

    def get_by_id(self, entry_id: int) -> Optional[AccountingEntry]:
        return self._db.query(AccountingEntry).filter(AccountingEntry.id == entry_id).first()

    def get_by_source_id(self, source_id: int) -> Optional[AccountingEntry]:
        return self._db.query(AccountingEntry).filter(AccountingEntry.source_id == source_id).first()

    def get_latest_by_document_id(self, document_id: int) -> Optional[AccountingEntry]:
        return (
            self._db.query(AccountingEntry)
            .filter(AccountingEntry.document_id == document_id)
            .order_by(AccountingEntry.extracted_at.desc(), AccountingEntry.id.desc())
            .first()
        )

    def get_all(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        move_type: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[AccountingEntry]:
        query = self._db.query(AccountingEntry)
        if date_from:
            query = query.filter(AccountingEntry.date >= date_from)
        if date_to:
            query = query.filter(AccountingEntry.date <= date_to)
        if move_type:
            query = query.filter(AccountingEntry.move_type == move_type)
        if state:
            query = query.filter(AccountingEntry.state == state)
        return query.order_by(AccountingEntry.date.desc(), AccountingEntry.id.desc()).all()

    def _log_match_failure(self, entry: AccountingEntry, nit: str) -> None:
        """Consultas diagnósticas para registrar el motivo exacto del fallo de match."""
        ref = f"entry id={entry.id} source_id={entry.source_id} name={entry.name!r}"

        # ¿Existe algún documento con ese NIT y fecha, independientemente del total?
        by_nit_date = self._db.execute(
            text(
                "SELECT id, total, accounting_entry_id IS NOT NULL AS already_linked "
                "FROM documents WHERE issuer_nit = :nit AND date = :date LIMIT 5"
            ),
            {"nit": nit, "date": str(entry.date)},
        ).fetchall()

        if not by_nit_date:
            # ¿Existe al menos un documento con ese NIT (ignorando fecha)?
            by_nit_only = self._db.execute(
                text("SELECT COUNT(*) FROM documents WHERE issuer_nit = :nit"),
                {"nit": nit},
            ).scalar()
            if by_nit_only:
                logger.warning(
                    "Sin match — %s | NIT=%s fecha=%s total=%.2f: "
                    "hay %d documento(s) con ese NIT pero ninguno en esa fecha.",
                    ref, nit, entry.date, float(entry.amount_total), by_nit_only,
                )
            else:
                logger.warning(
                    "Sin match — %s | NIT=%s fecha=%s total=%.2f: "
                    "no existe ningún documento con ese NIT en la base de datos.",
                    ref, nit, entry.date, float(entry.amount_total),
                )
            return

        already_linked = [r for r in by_nit_date if r[2]]
        available = [r for r in by_nit_date if not r[2]]

        if not available:
            logger.warning(
                "Sin match — %s | NIT=%s fecha=%s total=%.2f: "
                "se encontraron %d documento(s) con ese NIT y fecha pero todos ya tienen asiento vinculado "
                "(ids: %s).",
                ref, nit, entry.date, float(entry.amount_total),
                len(already_linked), [r[0] for r in already_linked],
            )
            return

        totals_disponibles = [float(r[1]) for r in available]
        logger.warning(
            "Sin match — %s | NIT=%s fecha=%s total=%.2f: "
            "hay %d documento(s) disponible(s) con ese NIT y fecha pero con total(es) diferente(s): %s "
            "(tolerancia ±%.2f COP).",
            ref, nit, entry.date, float(entry.amount_total),
            len(available), totals_disponibles, _AMOUNT_TOLERANCE,
        )

    def get_unmatched_in_invoices(self) -> List[AccountingEntry]:
        """Retorna todos los asientos in_invoice sin document_id asociado."""
        return (
            self._db.query(AccountingEntry)
            .filter(
                AccountingEntry.move_type == "in_invoice",
                AccountingEntry.document_id.is_(None),
            )
            .order_by(AccountingEntry.date.desc(), AccountingEntry.id.desc())
            .all()
        )
