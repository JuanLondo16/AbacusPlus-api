from fastapi import APIRouter, Depends

from app.application.dto.query import QueryRequest, QueryResponse
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.dependencies import get_query_with_rag_use_case

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consulta RAG-aumentada sobre facturas",
    description=(
        "Responde preguntas sobre las facturas almacenadas usando Retrieval-Augmented Generation (RAG).\n\n"
        "**Flujo interno:**\n"
        "1. Genera el embedding de la consulta.\n"
        "2. Recupera los `top_k` fragmentos más similares desde pgvector (rag-service).\n"
        "3. Construye un prompt aumentado con el contexto recuperado.\n"
        "4. Llama a OpenAI y retorna la respuesta junto con los chunks utilizados.\n\n"
        "**Ejemplos de consultas útiles:**\n"
        "- *¿Cuánto IVA pagó IKBO S.A.S en febrero?*\n"
        "- *Listar proveedores con facturas superiores a $1.000.000*\n"
        "- *¿Qué servicios facturó Monster Cakes?*"
    ),
    response_description="Respuesta generada por el LLM, consulta original, chunks de contexto usados y métricas de tokens.",
    responses={
        502: {"description": "Error de comunicación con OpenAI o con rag-service."},
    },
)
async def query_with_rag(
    request: QueryRequest,
    use_case: QueryWithRAGUseCase = Depends(get_query_with_rag_use_case),
):
    return await use_case.execute(request)
