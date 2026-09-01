from abc import ABC, abstractmethod
from typing import Optional


class AIServicePort(ABC):
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
    ) -> dict: ...


class RagClientPort(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        only_validated: bool = False,
        filters: Optional[dict] = None,
        min_similarity: Optional[float] = None,
    ) -> list[dict]: ...

    @abstractmethod
    async def index_chunk(self, source_type: str, source_id: int, content: str) -> None: ...
