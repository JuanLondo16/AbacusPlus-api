import logging
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.domain.entities.chunk import ChunkEntity
from app.domain.ports.repositories import ChunkRepositoryPort
from app.infrastructure.persistence.models.chunk import DocumentChunk

logger = logging.getLogger(__name__)


class ChunkRepository(ChunkRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def create(self, chunk: ChunkEntity) -> ChunkEntity:
        embedding_str = (
            f"[{','.join(map(str, chunk.embedding))}]" if chunk.embedding else None
        )
        db_chunk = DocumentChunk(
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            content=chunk.content,
        )
        self.db.add(db_chunk)
        self.db.flush()  # obtener el id antes del commit

        if embedding_str:
            self.db.execute(
                text("UPDATE document_chunks SET embedding = CAST(:emb AS vector) WHERE id = :id"),
                {"emb": embedding_str, "id": db_chunk.id},
            )

        self.db.commit()
        self.db.refresh(db_chunk)

        chunk.id = db_chunk.id
        chunk.created_at = db_chunk.created_at
        return chunk

    def search_similar(self, query_embedding: List[float], top_k: int = 5) -> List[dict]:
        """Búsqueda por similitud coseno usando el operador <=> de pgvector."""
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        rows = self.db.execute(
            text("""
                SELECT id, source_type, source_id, content,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM document_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :top_k
            """),
            {"emb": embedding_str, "top_k": top_k},
        ).fetchall()

        return [
            {
                "id": r[0],
                "source_type": r[1],
                "source_id": r[2],
                "content": r[3],
                "similarity": round(float(r[4]), 4),
            }
            for r in rows
        ]
