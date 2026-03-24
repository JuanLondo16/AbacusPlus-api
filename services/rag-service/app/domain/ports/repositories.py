from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.entities.chunk import ChunkEntity


class ChunkRepositoryPort(ABC):
    @abstractmethod
    def create(self, chunk: ChunkEntity) -> ChunkEntity:
        ...

    @abstractmethod
    def search_similar(self, query_embedding: List[float], top_k: int = 5) -> List[dict]:
        ...
