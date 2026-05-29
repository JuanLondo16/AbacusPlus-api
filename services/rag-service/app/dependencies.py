import os
from fastapi import Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.infrastructure.config.auth_dependency import get_tenant_db
from app.infrastructure.ai.ollama_service import OllamaEmbeddingService
from app.infrastructure.persistence.repositories.chunk_repository import ChunkRepository
from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase

load_dotenv()


def get_embedding_service() -> OllamaEmbeddingService:
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
