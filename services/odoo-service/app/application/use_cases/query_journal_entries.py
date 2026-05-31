import logging
from datetime import date
from typing import Optional

from app.application.dto.journal_entry import JournalEntryDetailResponse, JournalEntryResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.persistence.repositories.accounting_entry_repository import (
    AccountingEntryRepository,
)

logger = logging.getLogger(__name__)


class QueryJournalEntriesUseCase:
    def __init__(self, repository: AccountingEntryRepository):
        self._repo = repository

    def get_list(
        self,
        date_from: Optional[date],
        date_to: Optional[date],
        move_type: Optional[str],
        state: Optional[str],
    ) -> list[JournalEntryResponse]:
        entries = self._repo.get_all(
            date_from=date_from,
            date_to=date_to,
            move_type=move_type,
            state=state,
        )
        return [JournalEntryResponse.model_validate(e) for e in entries]

    def get_detail(self, entry_id: int) -> JournalEntryDetailResponse:
        entry = self._repo.get_by_id(entry_id)
        if not entry:
            raise EntityNotFoundException("AccountingEntry", str(entry_id))
        return JournalEntryDetailResponse.model_validate(entry)

    def get_latest_by_document_id(self, document_id: int) -> JournalEntryDetailResponse:
        entry = self._repo.get_latest_by_document_id(document_id)
        if not entry:
            raise EntityNotFoundException("AccountingEntry for document", str(document_id))
        return JournalEntryDetailResponse.model_validate(entry)
