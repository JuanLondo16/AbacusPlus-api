from abc import ABC, abstractmethod

from app.domain.entities.chunk import ChunkEntity


class ChunkRepositoryPort(ABC):
    @abstractmethod
    def create(self, chunk: ChunkEntity) -> ChunkEntity: ...

    @abstractmethod
    def search_similar(self, query_embedding: list[float], top_k: int = 5) -> list[dict]: ...
