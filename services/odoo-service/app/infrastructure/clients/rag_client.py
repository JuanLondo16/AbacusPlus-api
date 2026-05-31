import logging

import httpx

logger = logging.getLogger(__name__)


class RagClient:
    """
    Cliente HTTP síncrono para comunicarse con el rag-service (best-effort).
    Síncrono porque odoo-service usa endpoints y SQLAlchemy síncronos.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def index_chunk(self, source_type: str, source_id: int, content: str) -> dict:
        """
        Envía un fragmento de texto al rag-service para su indexación vectorial.
        Si el rag-service no está disponible se loguea el error pero no se propaga,
        para no bloquear la sincronización de asientos.
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._base_url}/api/v1/chunks",
                    json={
                        "source_type": source_type,
                        "source_id": source_id,
                        "content": content,
                    },
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning(
                "No se pudo indexar chunk en rag-service (source_id=%s): %s",
                source_id,
                exc,
            )
            return {}
