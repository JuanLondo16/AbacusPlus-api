import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class LlmClient:
    """Cliente HTTP para llamar al llm-service y obtener asientos contables."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def get_accounting_entry(self, document_id: int) -> Optional[dict]:
        """
        Consulta el último asiento contable generado para un documento.

        Llama a GET /api/v1/accounting/entries/{document_id} en llm-service
        y retorna el objeto `accounting_entry`, o None si no existe.
        """
        url = f"{self.base_url}/api/v1/accounting/entries/{document_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("accounting_entry")
                if response.status_code == 404:
                    return None
                logger.warning(
                    "llm-service retornó status %s para document_id=%s",
                    response.status_code,
                    document_id,
                )
                return None
        except httpx.RequestError as exc:
            logger.warning("No se pudo conectar a llm-service: %s", exc)
            return None
