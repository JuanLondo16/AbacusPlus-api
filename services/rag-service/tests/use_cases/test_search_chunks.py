"""Unit tests for SearchChunksUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.application.dto.chunk import SearchRequest
from app.application.use_cases.search_chunks import SearchChunksUseCase


@pytest.fixture
def fake_embedding_service():
    svc = AsyncMock()
    svc.embed = AsyncMock(return_value=[0.2] * 768)
    return svc


@pytest.fixture
def fake_chunk_repo():
    repo = MagicMock()
    repo.search_similar = MagicMock(
        return_value=[
            {
                "id": 1,
                "source_type": "invoice",
                "source_id": 10,
                "content": "Factura A",
                "similarity": 0.92,
            },
            {
                "id": 2,
                "source_type": "invoice",
                "source_id": 11,
                "content": "Factura B",
                "similarity": 0.85,
            },
        ]
    )
    return repo


class TestSearchChunksUseCase:
    async def test_returns_results(self, fake_chunk_repo, fake_embedding_service):
        use_case = SearchChunksUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )
        request = SearchRequest(query="facturas IVA", top_k=5)

        result = await use_case.execute(request)

        assert len(result.results) == 2
        assert result.query == "facturas IVA"

    async def test_similarity_scores_present(self, fake_chunk_repo, fake_embedding_service):
        use_case = SearchChunksUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )
        result = await use_case.execute(SearchRequest(query="test"))

        assert result.results[0].similarity == 0.92

    async def test_calls_embed_with_query(self, fake_chunk_repo, fake_embedding_service):
        use_case = SearchChunksUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )
        await use_case.execute(SearchRequest(query="mi consulta"))

        fake_embedding_service.embed.assert_called_once_with("mi consulta")
