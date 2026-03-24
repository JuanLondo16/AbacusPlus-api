from fastapi import APIRouter, Depends
from app.application.dto.query import QueryRequest, QueryResponse
from app.application.use_cases.query_with_rag import QueryWithRAGUseCase
from app.dependencies import get_query_with_rag_use_case

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_with_rag(
    request: QueryRequest,
    use_case: QueryWithRAGUseCase = Depends(get_query_with_rag_use_case),
):
    """Consulta aumentada con RAG: recupera contexto de facturas y responde con OpenAI."""
    return await use_case.execute(request)
