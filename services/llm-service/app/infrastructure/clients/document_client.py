import logging
from datetime import date
from typing import List, Optional
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

    async def list_by_date_range(
        self,
        dateini: date,
        datefin: date,
        status_filter: Optional[str] = None,
    ) -> List[dict]:
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
