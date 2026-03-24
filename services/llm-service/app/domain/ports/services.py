from abc import ABC, abstractmethod
from typing import List


class AIServicePort(ABC):
    @abstractmethod
    async def complete(self, prompt: str, model: str = "gpt-4o-mini") -> dict:
        ...


class RagClientPort(ABC):
    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        ...
