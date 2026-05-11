import logging
from typing import List

import httpx

logger = logging.getLogger(__name__)


class CatalogClient:
    """Cliente HTTP para obtener datos de catálogo desde xml-processor."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def _get(self, path: str) -> List[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def get_cost_centers(self) -> List[dict]:
        return await self._get("/api/v1/catalog/cost-centers")

    async def get_puc_accounts(self) -> List[dict]:
        return await self._get("/api/v1/catalog/puc-accounts")

    async def get_retention_fuente_rates(self) -> List[dict]:
        return await self._get("/api/v1/catalog/retention-fuente-rates")
