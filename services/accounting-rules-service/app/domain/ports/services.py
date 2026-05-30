from abc import ABC, abstractmethod
from typing import List


class EmbeddingServicePort(ABC):
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...
