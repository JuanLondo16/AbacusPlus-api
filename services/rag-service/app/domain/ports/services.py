from abc import ABC, abstractmethod


class EmbeddingServicePort(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...
