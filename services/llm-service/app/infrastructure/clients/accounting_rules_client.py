import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

_MISS_RESPONSE = {"match_level": "MISS", "confidence": 0.0, "suggested_entry": None, "known_fields": [], "explanation": "MISS: rules service unavailable."}


class AccountingRulesClient:
    """Cliente HTTP best-effort para consultar reglas de causación aprobadas."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def lookup_rules(
        self,
        issuer_nit: str,
        items: List[dict],
        document_id: Optional[int] = None,
    ) -> dict:
        """POST /api/v1/rules/lookups — best-effort, retorna MISS si falla."""
        payload = {"issuer_nit": issuer_nit, "items": items}
        if document_id is not None:
            payload["document_id"] = document_id
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/rules/lookups",
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo consultar accounting-rules-service (NIT=%s, doc=%s): %s",
                issuer_nit,
                document_id,
                exc,
            )
            return _MISS_RESPONSE
