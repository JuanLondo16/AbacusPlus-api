"""Unit tests for IndexChunkUseCase — repository and embedding service are mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.dto.chunk import IndexChunkRequest
from app.domain.entities.chunk import ChunkEntity


@pytest.fixture
def fake_embedding_service():
    svc = AsyncMock()
    svc.embed = AsyncMock(return_value=[0.1] * 768)
    svc.dimensions = 768
    return svc


@pytest.fixture
def fake_chunk_repo():
    repo = MagicMock()
    repo.create = MagicMock(side_effect=lambda chunk: ChunkEntity(
        id=1, source_type=chunk.source_type, source_id=chunk.source_id, content=chunk.content
    ))
    return repo


class TestIndexChunkUseCase:
    async def test_returns_correct_id_and_source_type(self, fake_chunk_repo, fake_embedding_service):
        use_case = IndexChunkUseCase(chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service)
        request = IndexChunkRequest(source_type="invoice", source_id=42, content="Factura de prueba")

        result = await use_case.execute(request)

        assert result.id == 1
        assert result.source_type == "invoice"
        assert result.source_id == 42

    async def test_calls_embed_with_content(self, fake_chunk_repo, fake_embedding_service):
        use_case = IndexChunkUseCase(chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service)
        request = IndexChunkRequest(source_type="file", content="Contenido del documento")

        await use_case.execute(request)

        fake_embedding_service.embed.assert_called_once_with("Contenido del documento")

    async def test_passes_embedding_to_repo(self, fake_chunk_repo, fake_embedding_service):
        use_case = IndexChunkUseCase(chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service)
        request = IndexChunkRequest(source_type="invoice", content="texto")

        await use_case.execute(request)

        saved_chunk = fake_chunk_repo.create.call_args[0][0]
        assert len(saved_chunk.embedding) == 768
