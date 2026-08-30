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

    async def trigger_retention_suggestion(self, document_id: int) -> None:
        """RF-08: determina las retenciones del tercero al procesar el documento.

        Se envía `persist=true` porque aquí no hay interfaz esperando la respuesta: la
        propuesta debe quedar guardada en el documento para que el contador la encuentre
        en la sección de retenciones y la confirme o la ajuste.

        Best-effort, igual que la asignación de cuentas: el documento ya está guardado y un
        fallo del llm-service no puede perderlo. El 409 (sin PUC o sin catálogo de
        impuestos) es una condición esperada y se registra sin ruido de error.
        """
        url = f"{self.base_url}/api/v1/accounting/retention-suggestions/{document_id}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url, headers=self._headers, params={"persist": "true"}
                )
                if response.status_code == 200:
                    persisted = response.json().get("persisted") or {}
                    logger.info(
                        "Retenciones automáticas doc=%s: created=%s skipped=%s",
                        document_id,
                        persisted.get("created", 0),
                        persisted.get("skipped", 0),
                    )
                elif response.status_code == 409:
                    logger.info(
                        "Retenciones automáticas omitidas para doc=%s: %s",
                        document_id,
                        response.json().get("detail"),
                    )
                else:
                    logger.warning(
                        "llm-service retornó status %s al sugerir retenciones para doc=%s",
                        response.status_code,
                        document_id,
                    )
        except Exception as exc:
            logger.warning(
                "No se pudo disparar la sugerencia de retenciones para doc=%s: %s",
                document_id,
                exc,
            )
