import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class DocumentClient:
    """Cliente HTTP para obtener documentos desde xml-processor."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def get_document(self, document_id: int) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._base_url}/api/v1/documents/{document_id}"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
