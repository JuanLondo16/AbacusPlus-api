"""Cliente síncrono del rag-service para el conocimiento contable (RF-08).

Existe junto al `RagClient` asíncrono por una razón práctica: la contabilización (RF-05) y la
reconciliación (RF-06) son casos de uso síncronos —toman un cerrojo de fila y hablan con
SIIGO en serie—, y el conocimiento se publica justo al cerrarlos. Meter una llamada
asíncrona en ese camino obligaría a arrastrar un bucle de eventos por toda la capa de
aplicación para ganar nada: la publicación es una única petición HTTP que ya es best-effort.

Cubre las dos operaciones del ciclo de vida del conocimiento: publicarlo cuando el documento
queda contabilizado y retirarlo cuando deja de estarlo.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class RagKnowledgeClient:
    """Publica y retira conocimiento validado en el rag-service (servicio-a-servicio)."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def index_chunk_internal(
        self,
        tenant_slug: str,
        source_type: str,
        source_id: int,
        content: str,
        is_validated: bool = False,
        siigo_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        embedding_text: Optional[str] = None,
    ) -> dict:
        return self._post(
            "/internal/chunks",
            {
                "tenant_slug": tenant_slug,
                "source_type": source_type,
                "source_id": source_id,
                "content": content,
                "embedding_text": embedding_text,
                "is_validated": is_validated,
                "siigo_id": siigo_id,
                "metadata": metadata or {},
            },
            source_id,
        )

    def revoke_chunks_internal(self, tenant_slug: str, source_type: str, source_id: int) -> dict:
        return self._post(
            "/internal/chunks/revoke",
            {"tenant_slug": tenant_slug, "source_type": source_type, "source_id": source_id},
            source_id,
        )

    # ── Transporte ─────────────────────────────────────────────────────────────

    def _post(self, path: str, body: dict, source_id: int) -> dict:
        """Best-effort: un fallo del RAG no puede deshacer lo que SIIGO ya aceptó.

        La contabilización es irreversible desde aquí; el conocimiento, en cambio, se puede
        reponer en cualquier momento con el backfill `/internal/documents/reindex`. Por eso
        el error se registra y no se propaga.
        """
        secret = os.environ.get("INTERNAL_SECRET", "")
        if not secret:
            logger.warning(
                "INTERNAL_SECRET no configurado; no se pudo llamar a %s (source_id=%s)",
                path,
                source_id,
            )
            return {}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    json=body,
                    headers={"X-Internal-Secret": secret},
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "rag-service no respondió a %s (source_id=%s): %s", path, source_id, exc
            )
            return {}


def build_rag_knowledge_client() -> RagKnowledgeClient:
    return RagKnowledgeClient(base_url=os.getenv("RAG_SERVICE_URL", "http://rag-service:8002"))
