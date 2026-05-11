import os
from fastapi import Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.infrastructure.config.database import get_db
from app.infrastructure.ai.openai_service import OpenAIService
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.clients.catalog_client import CatalogClient
from app.infrastructure.persistence.repositories.system_prompt_repository import SystemPromptRepository
from app.infrastructure.persistence.repositories.accounting_repository import AccountingRepository
from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase
from app.application.use_cases.query_accounting import QueryAccountingUseCase
from app.application.use_cases.recalculate_accounting_batch import RecalculateAccountingBatchUseCase

load_dotenv()


def get_openai_service() -> OpenAIService:
    api_key = os.getenv("OPENAI_API_KEY", "")
    return OpenAIService(api_key=api_key)


def get_rag_client() -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url)


def get_document_client() -> DocumentClient:
    url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    return DocumentClient(base_url=url)


def get_catalog_client() -> CatalogClient:
    url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    return CatalogClient(base_url=url)


def get_system_prompt_repo(db: Session = Depends(get_db)) -> SystemPromptRepository:
    return SystemPromptRepository(db)


def get_accounting_repo(db: Session = Depends(get_db)) -> AccountingRepository:
    return AccountingRepository(db)


def get_analyze_with_ai_use_case() -> AnalyzeWithAIUseCase:
    return AnalyzeWithAIUseCase(ai_service=get_openai_service())


def get_query_with_rag_use_case() -> QueryWithRAGUseCase:
    return QueryWithRAGUseCase(
        ai_service=get_openai_service(),
        rag_client=get_rag_client(),
    )


def get_generate_accounting_use_case(
    db: Session = Depends(get_db),
) -> GenerateAccountingEntryUseCase:
    return GenerateAccountingEntryUseCase(
        ai_service=get_openai_service(),
        rag_client=get_rag_client(),
        document_client=get_document_client(),
        catalog_client=get_catalog_client(),
        accounting_repo=AccountingRepository(db),
        system_prompt_repo=SystemPromptRepository(db),
    )


def get_query_accounting_use_case(
    db: Session = Depends(get_db),
) -> QueryAccountingUseCase:
    return QueryAccountingUseCase(
        document_client=get_document_client(),
        accounting_repo=AccountingRepository(db),
    )


def get_recalculate_accounting_batch_use_case(
    db: Session = Depends(get_db),
) -> RecalculateAccountingBatchUseCase:
    generate_use_case = GenerateAccountingEntryUseCase(
        ai_service=get_openai_service(),
        rag_client=get_rag_client(),
        document_client=get_document_client(),
        catalog_client=get_catalog_client(),
        accounting_repo=AccountingRepository(db),
        system_prompt_repo=SystemPromptRepository(db),
    )
    return RecalculateAccountingBatchUseCase(
        document_client=get_document_client(),
        generate_use_case=generate_use_case,
    )
