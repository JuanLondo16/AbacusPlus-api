import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.application.use_cases.assign_account_codes import AssignAccountCodesUseCase
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.infrastructure.ai.openai_service import OpenAIService
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.clients.integration_config_client import IntegrationConfigClient
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.auth_dependency import TokenData, get_tenant_db, get_token_data
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


def get_integration_config_client(
    token: Annotated[TokenData, Depends(get_token_data)],
) -> IntegrationConfigClient:
    url = os.getenv("INTEGRATION_CONFIG_URL", "http://integration-config-service:8007")
    return IntegrationConfigClient(base_url=url, bearer_token=token.raw_token)


def get_system_prompt_repo(db: Session = Depends(get_tenant_db)) -> SystemPromptRepository:
    return SystemPromptRepository(db)


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


def get_assign_account_codes_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> AssignAccountCodesUseCase:
    xml_url = os.getenv("XML_PROCESSOR_URL", "http://xml-processor:8001")
    integration_url = os.getenv("INTEGRATION_CONFIG_URL", "http://integration-config-service:8007")
    internal_secret = os.getenv("INTERNAL_SECRET", "")
    raw = token.raw_token if token else ""
    return AssignAccountCodesUseCase(
        ai_service=get_openai_service(),
        document_client=DocumentClient(
            base_url=xml_url,
            internal_secret=internal_secret,
            tenant_slug=token.tenant_slug,
        ),
        integration_config_client=IntegrationConfigClient(base_url=integration_url, bearer_token=raw),
        system_prompt_repo=SystemPromptRepository(db),
    )
