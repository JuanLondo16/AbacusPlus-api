from app.domain.ports.repositories import ChunkRepositoryPort
from app.domain.ports.services import EmbeddingServicePort
from app.application.dto.chunk import SearchRequest, SearchResponse, ChunkResult


class SearchChunksUseCase:
    def __init__(self, chunk_repo: ChunkRepositoryPort, embedding_service: EmbeddingServicePort):
        self._chunk_repo = chunk_repo
        self._embedding_service = embedding_service

    async def execute(self, request: SearchRequest) -> SearchResponse:
        query_embedding = await self._embedding_service.embed(request.query)
        results = self._chunk_repo.search_similar(query_embedding, top_k=request.top_k)

        return SearchResponse(
            query=request.query,
            results=[ChunkResult(**r) for r in results],
        )
