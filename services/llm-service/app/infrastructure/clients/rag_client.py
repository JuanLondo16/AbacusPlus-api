import logging
from typing import List
import httpx

from app.domain.ports.services import RagClientPort

logger = logging.getLogger(__name__)


class RagClient(RagClientPort):
    """Cliente HTTP para consultar el rag-service."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/chunks/search",
                json={"query": query, "top_k": top_k},
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json().get("results", [])

    async def index_chunk(self, source_type: str, source_id: int, content: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/chunks",
                    json={"source_type": source_type, "source_id": source_id, "content": content},
                    headers=self._headers,
                )
                response.raise_for_status()
        except Exception as e:
            logger.warning("No se pudo indexar asiento en RAG (source_id=%d): %s", source_id, e)
