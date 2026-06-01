import logging
from datetime import date
from typing import Optional

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class DocumentClient:
    """Cliente HTTP para obtener documentos desde xml-processor."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    def _raise_connection_error(self, exc: Exception) -> None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo conectar a xml-processor ({self._base_url}): {exc}",
        )

    async def get_document(self, document_id: int) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/documents/{document_id}",
                    headers=self._headers,
                )
        except httpx.TransportError as exc:
            self._raise_connection_error(exc)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def get_issuer(self, nit: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/issuers/{nit}",
                    headers=self._headers,
                )
        except httpx.TransportError as exc:
            self._raise_connection_error(exc)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def get_document_full(self, document_id: int) -> dict | None:
        """GET /documents/{id}/full — retorna documento con details enriquecidos (code, type, etc.)."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/documents/{document_id}/full",
                    headers=self._headers,
                )
        except httpx.TransportError as exc:
            self._raise_connection_error(exc)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def patch_detail_codes(self, document_id: int, assignments: list[dict]) -> int:
        """PATCH /documents/{id}/details — actualiza code y type en las líneas de detalle.

        Retorna cantidad de filas actualizadas. Best-effort: retorna 0 en fallo.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.patch(
                    f"{self._base_url}/api/v1/documents/{document_id}/details",
                    json=assignments,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json().get("updated", 0)
        except Exception as exc:
            logger.warning(
                "No se pudo actualizar códigos de detalle para doc=%s: %s", document_id, exc
            )
            return 0

    async def list_by_date_range(
        self,
        dateini: date,
        datefin: date,
        status_filter: Optional[str] = None,
    ) -> list[dict]:
        params = {"from_date": dateini.isoformat(), "to_date": datefin.isoformat()}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/documents",
                    params=params,
                    headers=self._headers,
                )
        except httpx.TransportError as exc:
            self._raise_connection_error(exc)
        response.raise_for_status()
        return response.json()
