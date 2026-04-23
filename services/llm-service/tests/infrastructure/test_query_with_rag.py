"""Unit tests for QueryWithRAGUseCase."""
import pytest
from unittest.mock import AsyncMock

from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.application.dto.query import QueryRequest
from app.domain.ports.services import AIServicePort, RagClientPort

_FAKE_USAGE = {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150}
_FAKE_CHUNKS = [
    {"id": 1, "source_type": "invoice", "source_id": 5, "content": "Factura A total 1000", "similarity": 0.9},
]


class FakeAIService(AIServicePort):
    async def complete(self, prompt: str, model: str = "gpt-4o-mini") -> dict:
        return {"content": f"Respuesta basada en: {prompt[:30]}", "usage": _FAKE_USAGE}


class FakeRagClient(RagClientPort):
    async def search(self, query: str, top_k: int = 5):
        return _FAKE_CHUNKS

    async def index_chunk(self, source_type: str, source_id: int, content: str) -> None:
        return None


class EmptyRagClient(RagClientPort):
    async def search(self, query: str, top_k: int = 5):
        return []

    async def index_chunk(self, source_type: str, source_id: int, content: str) -> None:
        return None


class TestQueryWithRAGUseCase:
    async def test_returns_response_with_context(self):
        use_case = QueryWithRAGUseCase(ai_service=FakeAIService(), rag_client=FakeRagClient())
        result = await use_case.execute(QueryRequest(query="¿Cuál es el total?"))

        assert result.response
        assert len(result.context_chunks) == 1
        assert result.context_chunks[0].similarity == 0.9

    async def test_returns_usage(self):
        use_case = QueryWithRAGUseCase(ai_service=FakeAIService(), rag_client=FakeRagClient())
        result = await use_case.execute(QueryRequest(query="test"))

        assert result.usage.total_tokens == 150

    async def test_works_without_rag_results(self):
        use_case = QueryWithRAGUseCase(ai_service=FakeAIService(), rag_client=EmptyRagClient())
        result = await use_case.execute(QueryRequest(query="pregunta sin contexto"))

        assert result.response
        assert result.context_chunks == []

    async def test_prompt_includes_context_when_chunks_exist(self):
        captured = {}

        class CapturingAI(AIServicePort):
            async def complete(self, prompt: str, model: str = "gpt-4o-mini") -> dict:
                captured["prompt"] = prompt
                return {"content": "ok", "usage": _FAKE_USAGE}

        use_case = QueryWithRAGUseCase(ai_service=CapturingAI(), rag_client=FakeRagClient())
        await use_case.execute(QueryRequest(query="¿cuánto es el IVA?"))

        assert "CONTEXTO" in captured["prompt"]
        assert "Factura A" in captured["prompt"]
