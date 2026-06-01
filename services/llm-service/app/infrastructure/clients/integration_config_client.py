import logging

import httpx

logger = logging.getLogger(__name__)


class IntegrationConfigClient:
    """Cliente HTTP para consultar catálogos del integration-config-service."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def get_chart_accounts(self, active_only: bool = True) -> list[dict]:
        """Retorna el plan de cuentas configurado.

        Llamada best-effort: retorna lista vacía si el servicio no está disponible.
        """
        params = {"active": "true"} if active_only else {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/integrations/chart-accounts",
                    params=params,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo obtener plan de cuentas de integration-config-service: %s", exc
            )
            return []
