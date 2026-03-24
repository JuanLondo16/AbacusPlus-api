from app.domain.entities.chunk import ChunkEntity
from app.domain.ports.repositories import ChunkRepositoryPort
from app.domain.ports.services import EmbeddingServicePort
from app.application.dto.chunk import IndexChunkRequest, IndexChunkResponse


class IndexChunkUseCase:
    def __init__(self, chunk_repo: ChunkRepositoryPort, embedding_service: EmbeddingServicePort):
        self._chunk_repo = chunk_repo
        self._embedding_service = embedding_service

    async def execute(self, request: IndexChunkRequest) -> IndexChunkResponse:
        embedding = await self._embedding_service.embed(request.content)

        chunk = ChunkEntity(
            source_type=request.source_type,
            source_id=request.source_id,
            content=request.content,
            embedding=embedding,
        )
        saved = self._chunk_repo.create(chunk)

        return IndexChunkResponse(
            id=saved.id,
            source_type=saved.source_type,
            source_id=saved.source_id,
        )
