import logging

from app.infrastructure.persistence.repositories.accounting_entry_repository import AccountingEntryRepository

logger = logging.getLogger(__name__)


class MatchEntriesUseCase:
    """
    Recorre todos los asientos in_invoice sin document_id y trata de vincularlos
    con un documento XML de la DIAN usando fecha, NIT (issuer_nit / partner_vat)
    y total (tolerancia ±1 COP).
    """

    def __init__(self, repository: AccountingEntryRepository):
        self._repo = repository

    def execute(self) -> dict:
        entries = self._repo.get_unmatched_in_invoices()
        total = len(entries)
        matched = 0
        unmatched = 0
        errors = []

        logger.info("Iniciando matching masivo: %d asientos in_invoice sin documento.", total)

        for entry in entries:
            try:
                document_id = self._repo.find_and_link_document(entry)
                if document_id:
                    matched += 1
                else:
                    unmatched += 1
            except Exception as exc:
                logger.error(
                    "Error al intentar vincular entry id=%s source_id=%s: %s",
                    entry.id, entry.source_id, exc, exc_info=True,
                )
                errors.append({"entry_id": entry.id, "source_id": entry.source_id, "error": str(exc)})

        logger.info(
            "Matching completado: total=%d matched=%d unmatched=%d errors=%d",
            total, matched, unmatched, len(errors),
        )

        return {
            "total_reviewed": total,
            "matched": matched,
            "unmatched": unmatched,
            "errors": errors,
        }
