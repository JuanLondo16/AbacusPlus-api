import os

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.match_entries import MatchEntriesUseCase
from app.application.use_cases.query_journal_entries import QueryJournalEntriesUseCase
from app.application.use_cases.sync_journal_entries import SyncJournalEntriesUseCase
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.auth_dependency import get_tenant_db
from app.infrastructure.odoo.odoo_client import OdooXmlRpcClient
from app.infrastructure.persistence.repositories.accounting_entry_repository import (
    AccountingEntryRepository,
)

load_dotenv()


def get_odoo_client() -> OdooXmlRpcClient:
    return OdooXmlRpcClient(
        url=os.getenv("ODOO_URL", "http://localhost:8069"),
        db=os.getenv("ODOO_DB", "odoo"),
        username=os.getenv("ODOO_USER", "admin"),
        password=os.getenv("ODOO_PASSWORD", "admin"),
    )


def get_rag_client() -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url)


def get_accounting_entry_repo(db: Session = Depends(get_tenant_db)) -> AccountingEntryRepository:
    return AccountingEntryRepository(db)


def get_sync_use_case(
    db: Session = Depends(get_tenant_db),
) -> SyncJournalEntriesUseCase:
    return SyncJournalEntriesUseCase(
        odoo_client=get_odoo_client(),
        repository=AccountingEntryRepository(db),
        rag_client=get_rag_client(),
    )


def get_query_use_case(
    db: Session = Depends(get_tenant_db),
) -> QueryJournalEntriesUseCase:
    return QueryJournalEntriesUseCase(
        repository=AccountingEntryRepository(db),
    )


def get_match_use_case(
    db: Session = Depends(get_tenant_db),
) -> MatchEntriesUseCase:
    return MatchEntriesUseCase(
        repository=AccountingEntryRepository(db),
    )
