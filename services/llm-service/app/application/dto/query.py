from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Pregunta o consulta sobre facturas")
    model: str = Field(default="gpt-4o-mini")
    top_k: int = Field(default=5, ge=1, le=20, description="Ejemplos RAG a recuperar")


class ContextChunk(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    content: str
    similarity: float


class AIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class QueryResponse(BaseModel):
    response: str
    model: str
    query: str
    context_chunks: List[ContextChunk]
    usage: AIUsage
