import os
from dotenv import load_dotenv

from app.infrastructure.ai.openai_service import OpenAIService
from app.infrastructure.clients.rag_client import RagClient
from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase

load_dotenv()


def get_openai_service() -> OpenAIService:
    api_key = os.getenv("OPENAI_API_KEY", "")
    return OpenAIService(api_key=api_key)


def get_rag_client() -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url)


def get_analyze_with_ai_use_case() -> AnalyzeWithAIUseCase:
    return AnalyzeWithAIUseCase(ai_service=get_openai_service())


def get_query_with_rag_use_case() -> QueryWithRAGUseCase:
    return QueryWithRAGUseCase(
        ai_service=get_openai_service(),
        rag_client=get_rag_client(),
    )
