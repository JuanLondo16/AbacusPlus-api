import logging
import uuid
from collections import defaultdict
from datetime import date
from typing import Optional

from app.domain.exceptions.base import ValidationException
from app.domain.ports.services import OdooClientPort
from app.application.dto.journal_entry import SyncRequest, SyncResponse
from app.infrastructure.persistence.repositories.journal_entry_repository import JournalEntryRepository

logger = logging.getLogger(__name__)

MAX_DATE_RANGE_DAYS = 366


class SyncJournalEntriesUseCase:

    def __init__(
        self,
        odoo_client: OdooClientPort,
        repository: JournalEntryRepository,
        rag_client=None,
    ):
        self._odoo = odoo_client
        self._repo = repository
        self._rag_client = rag_client

    def execute(self, request: SyncRequest) -> SyncResponse:
        self._validate(request)

        date_from = str(request.date_from)
        date_to = str(request.date_to)
        batch_id = str(uuid.uuid4())

        logger.info("Iniciando sync Odoo: %s → %s (batch=%s)", date_from, date_to, batch_id)

        moves = self._odoo.search_moves(date_from, date_to)

        if not moves:
            logger.info("No se encontraron asientos en el rango.")
            return SyncResponse(
                synced=0, created=0, updated=0,
                batch_id=batch_id, date_from=date_from, date_to=date_to, errors=[],
            )

        move_ids = [m["id"] for m in moves]

        # Batch: partners
        partner_ids = list({m["partner_id"][0] for m in moves if m.get("partner_id")})
        partner_map = self._odoo.get_partner_details(partner_ids) if partner_ids else {}

        # Batch: lines
        lines = self._odoo.get_move_lines(move_ids)

        # Batch: cuentas contables
        account_ids = list({
            ln["account_id"][0]
            for ln in lines
            if ln.get("account_id")
        })
        account_map = self._odoo.get_account_details(account_ids) if account_ids else {}

        # Batch: cuentas analíticas (centros de costo) — claves de analytic_distribution son strings
        # En Odoo 17 las claves pueden ser compuestas ("11,14") cuando una línea cruza varios planes.
        analytic_ids = list({
            int(part)
            for ln in lines
            if ln.get("analytic_distribution")
            for key in ln["analytic_distribution"].keys()
            for part in key.split(",")
            if part.strip().isdigit()
        })
        analytic_map = self._odoo.get_analytic_account_details(analytic_ids) if analytic_ids else {}

        # Agrupar líneas por id de asiento en Odoo
        lines_by_move: dict = defaultdict(list)
        for ln in lines:
            if ln.get("move_id"):
                lines_by_move[ln["move_id"][0]].append(ln)

        created = updated = 0
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

                # Indexar en RAG (best-effort, no bloquea el sync)
                if self._rag_client:
                    self._rag_client.index_chunk(
                        source_type="historical_entry",
                        source_id=entry.id,
                        content=self._build_chunk_content(entry),
                    )

            except Exception as exc:
                logger.error("Error procesando move source_id=%s: %s", move.get("id"), exc, exc_info=True)
                errors.append({"source_id": move.get("id"), "error": str(exc)})

        logger.info(
            "Sync completado: synced=%d created=%d updated=%d errors=%d",
            len(moves), created, updated, len(errors),
        )

        return SyncResponse(
            synced=len(moves),
            created=created,
            updated=updated,
            batch_id=batch_id,
            date_from=date_from,
            date_to=date_to,
            errors=errors,
        )

    def _build_chunk_content(self, entry) -> str:
        """
        Construye el texto del chunk para indexación semántica en RAG.
        Incluye cabecera del asiento y todas las líneas con cuentas PUC,
        débitos, créditos y centro de costo para que el LLM pueda inferir
        el tratamiento contable de facturas similares.
        """
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
