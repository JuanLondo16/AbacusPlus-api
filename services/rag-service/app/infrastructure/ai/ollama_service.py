from ollama import AsyncClient

from app.domain.ports.services import EmbeddingServicePort

_NOMIC_DIMENSIONS = 768
# nomic-embed-text: límite efectivo ~4050 chars ASCII; con español/números
# el tokenizador genera más tokens por char, se usa 3500 como límite seguro.
_MAX_CHARS = 3500


class OllamaEmbeddingService(EmbeddingServicePort):
    def __init__(self, host: str, model: str = "nomic-embed-text"):
        self._client = AsyncClient(host=host)
        self._model = model

    async def embed(self, text: str) -> list:
        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS]
        response = await self._client.embeddings(model=self._model, prompt=text)
        return response["embedding"]

    @property
    def dimensions(self) -> int:
        return _NOMIC_DIMENSIONS
