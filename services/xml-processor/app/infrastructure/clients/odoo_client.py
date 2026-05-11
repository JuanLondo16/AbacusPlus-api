import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class OdooClient:
    """Cliente HTTP para obtener causaciones contables sincronizadas desde Odoo."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def get_accounting_entry(self, document_id: int) -> Optional[dict]:
        """
        Consulta el último asiento contable vinculado a un documento.

        El `odoo-service` retorna el esquema nativo de Odoo; este cliente lo adapta
        al contrato usado por `GET /api/v1/documents/{id}/detail`.
        """
        url = f"{self.base_url}/api/v1/odoo/entries/by-document/{document_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    logger.warning(
                        "odoo-service retornó status %s para document_id=%s",
                        response.status_code,
                        document_id,
                    )
                    return None

                return self._to_document_detail_accounting(response.json())
        except httpx.RequestError as exc:
            logger.warning("No se pudo conectar a odoo-service: %s", exc)
            return None

    def _to_document_detail_accounting(self, entry: dict) -> dict:
        lines = [
            {
                "id": line.get("id"),
                "cuenta": line.get("account_code") or "",
                "nombre": line.get("account_name") or line.get("name") or "",
                "debito": float(line.get("debit") or 0),
                "credito": float(line.get("credit") or 0),
                "tercero": line.get("partner_name"),
                "centro_costo": line.get("cost_center"),
                "descripcion": line.get("name"),
            }
            for line in entry.get("lines", [])
        ]
        return {
            "id": entry.get("id"),
            "model_used": None,
            "status": entry.get("state") or "synced",
            "lines": lines,
            "created_at": entry.get("extracted_at"),
        }
