from fastapi import APIRouter, Depends, status

from app.application.dto.chunk import IndexChunkRequest, IndexChunkResponse, SearchRequest, SearchResponse
from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase
from app.dependencies import get_index_chunk_use_case, get_search_chunks_use_case

router = APIRouter()


@router.post("/chunks", response_model=IndexChunkResponse, status_code=status.HTTP_201_CREATED)
async def index_chunk(
    request: IndexChunkRequest,
    use_case: IndexChunkUseCase = Depends(get_index_chunk_use_case),
):
    """Recibe un fragmento de texto, genera su embedding y lo almacena en pgvector."""
    return await use_case.execute(request)


@router.post("/chunks/search", response_model=SearchResponse)
async def search_chunks(
    request: SearchRequest,
    use_case: SearchChunksUseCase = Depends(get_search_chunks_use_case),
):
    """Busca los fragmentos más similares a la consulta usando similitud coseno."""
    return await use_case.execute(request)
