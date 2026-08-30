from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.config.database import Base

EMBEDDING_DIMENSIONS = 1536  # OpenAI text-embedding-3-small


class DocumentChunk(Base):
    """Fragmento de texto con embedding vectorial para búsqueda semántica (RAG)."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), nullable=False)  # 'invoice' | 'file'
    source_id = Column(Integer, nullable=True)  # FK lógica a documents.id
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── RF-08: conocimiento validado ───────────────────────────────────────────
    #
    # `is_validated` marca los chunks que representan una causación que superó TODO el flujo
    # operativo y quedó contabilizada en SIIGO. Es la única clase de conocimiento que puede
    # servir de precedente para sugerir la causación de documentos posteriores.
    #
    # Se guarda como columna y no como un `source_type` distinto porque el estado del
    # conocimiento cambia con el ciclo de vida del documento (una causación contabilizada
    # puede invalidarse después por un ajuste o una reversión), mientras que el tipo de
    # fuente no cambia nunca.
    is_validated = Column(Boolean, nullable=False, default=False, server_default="false")
    #: Momento en que el documento quedó CONTABILIZADO y el conocimiento se dio por válido.
    validated_at = Column(DateTime, nullable=True)
    #: Identificador de la factura en SIIGO. Es la prueba de que la causación se contabilizó
    #: de verdad, y la referencia con la que auditar el conocimiento contra la contabilidad.
    siigo_id = Column(String(100), nullable=True)

    # ── RF-08: rasgos estructurados del caso, para la búsqueda híbrida ─────────
    #
    # La similitud entre dos facturas no es un asunto de parecido textual. Dos documentos
    # del mismo proveedor y el mismo concepto son el precedente que se busca aunque sus
    # descripciones no compartan una palabra; y dos textos casi idénticos de proveedores
    # distintos, con régimen distinto, llevan a retenciones distintas. El embedding no
    # distingue esos casos porque no sabe qué es un NIT.
    #
    # Aquí se guardan los rasgos que SÍ discriminan —NIT del emisor, municipio, cuentas,
    # tipos de retención practicados— para poder filtrar por ellos ANTES de ordenar por
    # similitud. Ninguno es un dato nuevo: todos existen ya en el documento contabilizado.
    doc_metadata = Column("metadata", JSONB, nullable=False, server_default="{}")


# La búsqueda de conocimiento filtra por `is_validated` y el upsert por documento localiza
# los chunks por (source_type, source_id); ambos accesos se apoyan en estos índices.
Index("ix_document_chunks_source", DocumentChunk.source_type, DocumentChunk.source_id)
Index("ix_document_chunks_is_validated", DocumentChunk.is_validated)
# GIN sobre el JSONB: es lo que hace barato el filtro estructurado de la búsqueda híbrida.
Index(
    "ix_document_chunks_metadata",
    DocumentChunk.doc_metadata,
    postgresql_using="gin",
)
