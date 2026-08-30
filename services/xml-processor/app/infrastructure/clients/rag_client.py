import logging
import os

import httpx

logger = logging.getLogger(__name__)


class RagClient:
    """Cliente HTTP para comunicarse con el rag-service."""

    def __init__(self, base_url: str, bearer_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def index_chunk(self, source_type: str, source_id: int, content: str) -> dict:
        """Envía un fragmento de texto al rag-service para su indexación vectorial.

        La llamada es best-effort: si el rag-service no está disponible se loguea
        el error pero no se propaga, para no bloquear el procesamiento del XML.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/chunks",
                    json={"source_type": source_type, "source_id": source_id, "content": content},
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo indexar chunk en rag-service (source_id=%s): %s", source_id, exc
            )
            return {}

    async def index_chunk_internal(
        self,
        tenant_slug: str,
        source_type: str,
        source_id: int,
        content: str,
        is_validated: bool = False,
        siigo_id: str = "",
    ) -> dict:
        """Indexa un chunk vía la ruta interna del rag-service (servicio-a-servicio).

        La usan los procesos que corren sin sesión de usuario: en vez de un JWT, autentican
        con `X-Internal-Secret` y pasan el `tenant_slug` explícito para que el rag-service
        escriba en la BD del tenant correcto. Best-effort igual que `index_chunk`.

        RF-08: `is_validated` y `siigo_id` marcan el chunk como conocimiento contable
        reutilizable. Solo deben llegar informados desde el cierre de la contabilización,
        cuando el documento ya está en «Contabilizada» con el comprobante de SIIGO; el
        rag-service rechaza un chunk validado sin `siigo_id`.
        """
        secret = os.environ.get("INTERNAL_SECRET", "")
        if not secret:
            logger.warning(
                "INTERNAL_SECRET no configurado; no se indexa chunk interno (source_id=%s)",
                source_id,
            )
            return {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/internal/chunks",
                    json={
                        "tenant_slug": tenant_slug,
                        "source_type": source_type,
                        "source_id": source_id,
                        "content": content,
                        "is_validated": is_validated,
                        "siigo_id": siigo_id or None,
                    },
                    headers={"X-Internal-Secret": secret},
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo indexar chunk interno en rag-service (tenant=%s, source_id=%s): %s",
                tenant_slug,
                source_id,
                exc,
            )
            return {}

    async def revoke_chunks_internal(
        self, tenant_slug: str, source_type: str, source_id: int
    ) -> dict:
        """RF-08: retira del RAG el conocimiento de un documento (servicio-a-servicio).

        Se llama cuando una causación contabilizada deja de ser válida (ajuste o reversión).
        Best-effort como el resto del cliente: si el rag-service no responde se registra el
        aviso, y el conocimiento obsoleto se limpia en el siguiente backfill.
        """
        secret = os.environ.get("INTERNAL_SECRET", "")
        if not secret:
            logger.warning(
                "INTERNAL_SECRET no configurado; no se retira el chunk (source_id=%s)", source_id
            )
            return {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/internal/chunks/revoke",
                    json={
                        "tenant_slug": tenant_slug,
                        "source_type": source_type,
                        "source_id": source_id,
                    },
                    headers={"X-Internal-Secret": secret},
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo retirar el chunk del rag-service (tenant=%s, source_id=%s): %s",
                tenant_slug,
                source_id,
                exc,
            )
            return {}
