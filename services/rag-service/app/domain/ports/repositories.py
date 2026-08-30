from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities.chunk import ChunkEntity


class ChunkRepositoryPort(ABC):
    @abstractmethod
    def create(self, chunk: ChunkEntity) -> ChunkEntity: ...

    @abstractmethod
    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        only_validated: bool = False,
        filters: Optional[dict] = None,
        min_similarity: float = 0.0,
    ) -> list[dict]: ...

    @abstractmethod
    def delete_by_source(self, source_type: str, source_id: int) -> int: ...
