import httpx

from app.domain.ports.services import EmbeddingServicePort

# text-embedding-3-small → 1536 dimensiones. Debe coincidir con EMBEDDING_DIMENSIONS en
# infrastructure/persistence/models/chunk.py y con la dimensión de la columna pgvector.
_DIMENSIONS = 1536
# text-embedding-3 admite ~8191 tokens; el contenido de un chunk (factura resumida) es muy
# inferior, pero se acota por defensa ante documentos con muchas líneas.
_MAX_CHARS = 8000


class OpenAIEmbeddingService(EmbeddingServicePort):
    """Genera embeddings con la API de OpenAI (mismo puerto que el servicio de Ollama).

    Se llama por HTTP con httpx —igual que el resto de clientes del proyecto— para no añadir
    el SDK de OpenAI como dependencia ni reconstruir la imagen del rag-service.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def embed(self, text: str) -> list[float]:
        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS
