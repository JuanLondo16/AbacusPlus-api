import logging

import httpx

logger = logging.getLogger(__name__)


class CatalogClient:
    """Cliente HTTP para obtener datos de catálogo desde xml-processor."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def _get(self, path: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}{path}", headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def get_cost_centers(self) -> list[dict]:
        return await self._get("/api/v1/catalog/cost-centers")

    async def get_puc_accounts(self) -> list[dict]:
        return await self._get("/api/v1/catalog/puc-accounts")

    async def get_retention_fuente_rates(self) -> list[dict]:
        return await self._get("/api/v1/catalog/retention-fuente-rates")
