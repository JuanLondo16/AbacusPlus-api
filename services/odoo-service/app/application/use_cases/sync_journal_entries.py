import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterator

from app.application.dto.journal_entry import SyncRequest, SyncResponse
from app.domain.exceptions.base import ValidationException
from app.domain.ports.services import OdooClientPort
from app.infrastructure.persistence.repositories.accounting_entry_repository import (
    AccountingEntryRepository,
)

logger = logging.getLogger(__name__)

MAX_DATE_RANGE_DAYS = 366
BATCH_SIZE_DAYS = 10


def _date_batches(date_from: date, date_to: date) -> Iterator[tuple[date, date]]:
    """Divide el rango en ventanas de BATCH_SIZE_DAYS días."""
    current = date_from
    while current <= date_to:
        end = min(current + timedelta(days=BATCH_SIZE_DAYS - 1), date_to)
        yield current, end
        current = end + timedelta(days=1)


class SyncJournalEntriesUseCase:
    def __init__(
        self,
        odoo_client: OdooClientPort,
        repository: AccountingEntryRepository,
        rag_client=None,
    ):
        self._odoo = odoo_client
        self._repo = repository
        self._rag_client = rag_client

    def execute(self, request: SyncRequest) -> SyncResponse:
        self._validate(request)

        batch_id = str(uuid.uuid4())
        date_from_str = str(request.date_from)
        date_to_str = str(request.date_to)

        batches = list(_date_batches(request.date_from, request.date_to))
        logger.info(
            "Iniciando sync Odoo: %s → %s | lotes=%d (batch=%s)",
            date_from_str,
            date_to_str,
            len(batches),
            batch_id,
        )

        total_synced = created = updated = matched = 0
        errors = []

        for batch_from, batch_to in batches:
            s, c, u, m, e = self._process_batch(str(batch_from), str(batch_to), batch_id)
            total_synced += s
            created += c
            updated += u
            matched += m
            errors.extend(e)

        logger.info(
            "Sync completado: synced=%d created=%d updated=%d matched=%d errors=%d",
            total_synced,
            created,
            updated,
            matched,
            len(errors),
        )

        return SyncResponse(
            synced=total_synced,
            created=created,
            updated=updated,
            matched=matched,
            batch_id=batch_id,
            date_from=date_from_str,
            date_to=date_to_str,
            errors=errors,
        )

    def _process_batch(
        self,
        date_from: str,
        date_to: str,
        batch_id: str,
    ) -> tuple[int, int, int, int, list]:
        """
        Procesa un lote de 10 días. Retorna (synced, created, updated, matched, errors).
        """
        logger.info("  Lote %s → %s", date_from, date_to)

        moves = self._odoo.search_moves(date_from, date_to)
        if not moves:
            return 0, 0, 0, 0, []

        move_ids = [m["id"] for m in moves]

        partner_ids = list({m["partner_id"][0] for m in moves if m.get("partner_id")})
        partner_map = self._odoo.get_partner_details(partner_ids) if partner_ids else {}

        lines = self._odoo.get_move_lines(move_ids)

        account_ids = list({ln["account_id"][0] for ln in lines if ln.get("account_id")})
        account_map = self._odoo.get_account_details(account_ids) if account_ids else {}

        analytic_ids = list(
            {
                int(part)
                for ln in lines
                if ln.get("analytic_distribution")
                for key in ln["analytic_distribution"]
                for part in key.split(",")
                if part.strip().isdigit()
            }
        )
        analytic_map = self._odoo.get_analytic_account_details(analytic_ids) if analytic_ids else {}

        lines_by_move: dict = defaultdict(list)
        for ln in lines:
            if ln.get("move_id"):
                lines_by_move[ln["move_id"][0]].append(ln)

        created = updated = matched = 0
        errors = []

        for move in moves:
            try:
                move_lines = lines_by_move.get(move["id"], [])
                entry, is_new = self._repo.upsert_entry(
                    move, move_lines, partner_map, account_map, analytic_map, batch_id
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

                document_id = self._repo.find_and_link_document(entry)
                if document_id:
                    matched += 1

                if self._rag_client:
                    self._rag_client.index_chunk(
                        source_type="accounting_entry",
                        source_id=entry.id,
                        content=self._build_chunk_content(entry),
                    )

            except Exception as exc:
                logger.error(
                    "Error procesando move source_id=%s: %s", move.get("id"), exc, exc_info=True
                )
                errors.append({"source_id": move.get("id"), "error": str(exc)})

        return len(moves), created, updated, matched, errors

    def _build_chunk_content(self, entry) -> str:
        lines_text = ""
        for line in entry.lines:
            account_code = line.account_code or ""
            account_name = line.account_name or ""
            debit = float(line.debit or 0)
            credit = float(line.credit or 0)
            cost_center = line.cost_center or ""
            lines_text += (
                f"  {account_code} {account_name} | "
                f"Débito: {debit:.2f} | Crédito: {credit:.2f} | CC: {cost_center}\n"
            )

        return (
            f"Asiento: {entry.name or ''} | Tipo: {entry.move_type or ''} | "
            f"Fecha: {entry.date or ''} | Diario: {entry.journal_name or ''}\n"
            f"Tercero: {entry.partner_name or ''} | NIT: {entry.partner_vat or ''}\n"
            f"Base imponible: {float(entry.amount_untaxed):.2f} | "
            f"IVA: {float(entry.amount_tax):.2f} | "
            f"Total: {float(entry.amount_total):.2f}\n"
            f"Líneas contables:\n{lines_text}"
        ).strip()

    def _validate(self, request: SyncRequest) -> None:
        if request.date_from > request.date_to:
            raise ValidationException("date_from no puede ser posterior a date_to.")
        delta = (request.date_to - request.date_from).days
        if delta > MAX_DATE_RANGE_DAYS:
            raise ValidationException(
                f"El rango de fechas no puede superar {MAX_DATE_RANGE_DAYS} días."
            )
