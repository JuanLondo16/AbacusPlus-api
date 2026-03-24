from pydantic import BaseModel, Field
from typing import Optional, List


class IndexChunkRequest(BaseModel):
    source_type: str = Field(..., description="Tipo de fuente: 'invoice' | 'file'")
    source_id: Optional[int] = Field(None, description="ID del documento origen")
    content: str = Field(..., min_length=1, description="Texto a indexar")


class IndexChunkResponse(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    message: str = "Chunk indexado correctamente"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Texto de consulta para búsqueda semántica")
    top_k: int = Field(default=5, ge=1, le=20, description="Número máximo de resultados")


class ChunkResult(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    content: str
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: List[ChunkResult]
