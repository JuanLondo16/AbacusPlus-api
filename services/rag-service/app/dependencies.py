import os

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase
from app.domain.ports.services import EmbeddingServicePort
from app.infrastructure.ai.ollama_service import OllamaEmbeddingService
from app.infrastructure.ai.openai_embedding_service import OpenAIEmbeddingService
from app.infrastructure.config.auth_dependency import get_tenant_db
from app.infrastructure.persistence.repositories.chunk_repository import ChunkRepository

load_dotenv()


def get_embedding_service() -> EmbeddingServicePort:
    """Proveedor de embeddings del RAG.

    Por defecto OpenAI (`text-embedding-3-small`, 1536 dim), que es lo que usa el proyecto
    para el razonamiento y ahora también para los vectores. Si no hay `OPENAI_API_KEY`, cae a
    Ollama local (`nomic-embed-text`, 768 dim) para no dejar el servicio inoperante en
    entornos sin key. IMPORTANTE: la dimensión debe coincidir con `EMBEDDING_DIMENSIONS` del
    modelo y con la columna pgvector; no mezclar proveedores de distinta dimensión sin migrar.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddingService(api_key=api_key, model=model)
    host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    return OllamaEmbeddingService(host=host, model=model)


def get_index_chunk_use_case(
    db: Session = Depends(get_tenant_db),
    embedding_service: OllamaEmbeddingService = Depends(get_embedding_service),
) -> IndexChunkUseCase:
    return IndexChunkUseCase(
        chunk_repo=ChunkRepository(db),
        embedding_service=embedding_service,
    )


def get_search_chunks_use_case(
    db: Session = Depends(get_tenant_db),
    embedding_service: OllamaEmbeddingService = Depends(get_embedding_service),
) -> SearchChunksUseCase:
    return SearchChunksUseCase(
        chunk_repo=ChunkRepository(db),
        embedding_service=embedding_service,
    )
