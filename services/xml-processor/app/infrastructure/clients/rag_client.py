import logging
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
            logger.warning("No se pudo indexar chunk en rag-service (source_id=%s): %s", source_id, exc)
            return {}
