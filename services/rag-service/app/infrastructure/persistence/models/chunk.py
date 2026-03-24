from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from pgvector.sqlalchemy import Vector
from app.infrastructure.config.database import Base

EMBEDDING_DIMENSIONS = 768


class DocumentChunk(Base):
    """Fragmento de texto con embedding vectorial para búsqueda semántica (RAG)."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), nullable=False)   # 'invoice' | 'file'
    source_id = Column(Integer, nullable=True)          # FK lógica a documents.id
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
