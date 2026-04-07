from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Pregunta o consulta sobre las facturas indexadas.",
        examples=["¿Cuánto IVA pagó IKBO S.A.S en el mes de marzo?"],
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Modelo de OpenAI a utilizar.",
        examples=["gpt-4o-mini", "gpt-4o"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Número de fragmentos RAG a recuperar como contexto. Valores más altos mejoran la precisión pero aumentan el costo.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "¿Qué servicios facturó Monster Cakes en el último mes?",
                "model": "gpt-4o-mini",
                "top_k": 5,
            }
        }
    }


class ContextChunk(BaseModel):
    id: int = Field(..., description="ID del chunk en la base de datos vectorial.")
    source_type: str = Field(..., description="Tipo de fuente del chunk (ej: `document`).")
    source_id: Optional[int] = Field(None, description="ID del documento origen del chunk.")
    content: str = Field(..., description="Texto del fragmento recuperado.")
    similarity: float = Field(..., description="Score de similitud coseno con la consulta (0.0 a 1.0).")


class AIUsage(BaseModel):
    prompt_tokens: int = Field(..., description="Tokens consumidos por el prompt.")
    completion_tokens: int = Field(..., description="Tokens consumidos por la respuesta generada.")
    total_tokens: int = Field(..., description="Total de tokens consumidos en la llamada.")


class QueryResponse(BaseModel):
    response: str = Field(..., description="Respuesta generada por el LLM con base en el contexto RAG.")
    model: str = Field(..., description="Modelo de OpenAI que procesó la solicitud.")
    query: str = Field(..., description="Consulta original del usuario.")
    context_chunks: List[ContextChunk] = Field(..., description="Fragmentos recuperados del RAG utilizados como contexto.")
    usage: AIUsage = Field(..., description="Métricas de consumo de tokens.")
