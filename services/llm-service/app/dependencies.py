import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase
from app.application.use_cases.query_accounting import QueryAccountingUseCase
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.application.use_cases.recalculate_accounting_batch import RecalculateAccountingBatchUseCase
from app.application.use_cases.recalculate_accounting_document import (
    RecalculateAccountingDocumentUseCase,
)
from app.infrastructure.ai.openai_service import OpenAIService
from app.infrastructure.clients.accounting_rules_client import AccountingRulesClient
from app.infrastructure.clients.catalog_client import CatalogClient
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.auth_dependency import TokenData, get_tenant_db, get_token_data
from app.infrastructure.persistence.repositories.accounting_repository import AccountingRepository
from app.infrastructure.persistence.repositories.chart_account_repository import (
    ChartAccountRepository,
)
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

load_dotenv()


def get_openai_service() -> OpenAIService:
    api_key = os.getenv("OPENAI_API_KEY", "")
    return OpenAIService(api_key=api_key)


def get_rag_client(token: Annotated[TokenData, Depends(get_token_data)]) -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url, bearer_token=token.raw_token)


def get_document_client(token: Annotated[TokenData, Depends(get_token_data)]) -> DocumentClient:
    url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    return DocumentClient(base_url=url, bearer_token=token.raw_token)


def get_catalog_client(token: Annotated[TokenData, Depends(get_token_data)]) -> CatalogClient:
    url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    return CatalogClient(base_url=url, bearer_token=token.raw_token)


def get_system_prompt_repo(db: Session = Depends(get_tenant_db)) -> SystemPromptRepository:
    return SystemPromptRepository(db)


def get_accounting_repo(db: Session = Depends(get_tenant_db)) -> AccountingRepository:
    return AccountingRepository(db)


def get_analyze_with_ai_use_case() -> AnalyzeWithAIUseCase:
    return AnalyzeWithAIUseCase(ai_service=get_openai_service())


def get_query_with_rag_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
) -> QueryWithRAGUseCase:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return QueryWithRAGUseCase(
        ai_service=get_openai_service(),
        rag_client=RagClient(base_url=url, bearer_token=token.raw_token),
    )


def get_accounting_rules_client(
    token: Annotated[TokenData, Depends(get_token_data)],
) -> AccountingRulesClient:
    url = os.getenv("ACCOUNTING_RULES_SERVICE_URL", "http://accounting-rules-service:8009")
    return AccountingRulesClient(base_url=url, bearer_token=token.raw_token)


def get_generate_accounting_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> GenerateAccountingEntryUseCase:
    xml_url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    rules_url = os.getenv("ACCOUNTING_RULES_SERVICE_URL", "http://accounting-rules-service:8009")
    raw = token.raw_token if token else ""
    return GenerateAccountingEntryUseCase(
        ai_service=get_openai_service(),
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        catalog_client=CatalogClient(base_url=xml_url, bearer_token=raw),
        accounting_repo=AccountingRepository(db),
        system_prompt_repo=SystemPromptRepository(db),
        chart_account_repo=ChartAccountRepository(db),
        accounting_rules_client=AccountingRulesClient(base_url=rules_url, bearer_token=raw),
    )


def get_query_accounting_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> QueryAccountingUseCase:
    xml_url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    raw = token.raw_token if token else ""
    return QueryAccountingUseCase(
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        accounting_repo=AccountingRepository(db),
    )


def get_recalculate_accounting_batch_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> RecalculateAccountingBatchUseCase:
    xml_url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    raw = token.raw_token if token else ""
    generate_use_case = GenerateAccountingEntryUseCase(
        ai_service=get_openai_service(),
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        catalog_client=CatalogClient(base_url=xml_url, bearer_token=raw),
        accounting_repo=AccountingRepository(db),
        system_prompt_repo=SystemPromptRepository(db),
        chart_account_repo=ChartAccountRepository(db),
    )
    return RecalculateAccountingBatchUseCase(
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        generate_use_case=generate_use_case,
    )


def get_recalculate_accounting_document_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> RecalculateAccountingDocumentUseCase:
    xml_url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    raw = token.raw_token if token else ""
    generate_use_case = GenerateAccountingEntryUseCase(
        ai_service=get_openai_service(),
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        catalog_client=CatalogClient(base_url=xml_url, bearer_token=raw),
        accounting_repo=AccountingRepository(db),
        system_prompt_repo=SystemPromptRepository(db),
        chart_account_repo=ChartAccountRepository(db),
    )
    return RecalculateAccountingDocumentUseCase(
        document_client=DocumentClient(base_url=xml_url, bearer_token=raw),
        generate_use_case=generate_use_case,
    )
