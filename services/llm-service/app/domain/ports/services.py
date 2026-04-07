from abc import ABC, abstractmethod
from typing import List, Optional


class AIServicePort(ABC):
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
    ) -> dict:
        ...


class RagClientPort(ABC):
    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        ...
