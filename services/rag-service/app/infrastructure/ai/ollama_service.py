from ollama import AsyncClient
from app.domain.ports.services import EmbeddingServicePort

_NOMIC_DIMENSIONS = 768


class OllamaEmbeddingService(EmbeddingServicePort):
    def __init__(self, host: str, model: str = "nomic-embed-text"):
        self._client = AsyncClient(host=host)
        self._model = model

    async def embed(self, text: str) -> list:
        response = await self._client.embeddings(model=self._model, prompt=text)
        return response["embedding"]

    @property
    def dimensions(self) -> int:
        return _NOMIC_DIMENSIONS
