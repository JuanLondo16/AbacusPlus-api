import logging

import httpx

logger = logging.getLogger(__name__)


class LlmClient:
    """Cliente HTTP para llamar al llm-service."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def trigger_code_assignment(self, document_id: int) -> None:
        """Dispara la asignación de cuentas PUC en llm-service. Best-effort."""
        url = f"{self.base_url}/api/v1/accounting/code-assignments/{document_id}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self._headers)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        "Asignación PUC doc=%s: assigned=%s skipped=%s",
                        document_id,
                        data.get("assigned"),
                        data.get("skipped"),
                    )
                else:
                    logger.warning(
                        "llm-service retornó status %s al asignar cuentas para doc=%s",
                        response.status_code,
                        document_id,
                    )
        except Exception as exc:
            logger.warning(
                "No se pudo disparar asignación de cuentas para doc=%s: %s", document_id, exc
            )
