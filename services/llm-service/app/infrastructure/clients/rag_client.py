import logging
from typing import List
import httpx

from app.domain.ports.services import RagClientPort

logger = logging.getLogger(__name__)


class RagClient(RagClientPort):
    """Cliente HTTP para consultar el rag-service."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/chunks/search",
                json={"query": query, "top_k": top_k},
            )
            response.raise_for_status()
            return response.json().get("results", [])
