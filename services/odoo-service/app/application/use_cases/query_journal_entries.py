import logging
from datetime import date
from typing import List, Optional

from app.domain.exceptions.base import EntityNotFoundException
from app.application.dto.journal_entry import JournalEntryResponse, JournalEntryDetailResponse
from app.infrastructure.persistence.repositories.accounting_entry_repository import AccountingEntryRepository

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
    ) -> List[JournalEntryResponse]:
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
