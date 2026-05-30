import logging

import httpx

logger = logging.getLogger(__name__)


class AccountingRulesClient:
    """Cliente HTTP best-effort para notificar aprobaciones al accounting-rules-service."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def notify_approval(self, payload: dict) -> dict:
        """POST /api/v1/rules/approvals — best-effort, nunca bloquea el flujo principal."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/rules/approvals",
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo notificar aprobación a accounting-rules-service (doc=%s): %s",
                payload.get("document_id"),
                exc,
            )
            return {}
