from fastapi import APIRouter, Depends, status

from app.application.dto.chunk import IndexChunkRequest, IndexChunkResponse, SearchRequest, SearchResponse
from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase
from app.dependencies import get_index_chunk_use_case, get_search_chunks_use_case

router = APIRouter()


@router.post(
    "/chunks",
    response_model=IndexChunkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Indexar fragmento de texto con embedding",
    description=(
        "Recibe un fragmento de texto, genera su embedding vectorial usando Ollama "
        "(`nomic-embed-text`, 768 dimensiones) y lo almacena en PostgreSQL con pgvector.\n\n"
        "Este endpoint es llamado automáticamente por xml-processor tras procesar cada factura. "
        "También puede usarse directamente para indexar contenido adicional.\n\n"
        "Los chunks son la base del sistema RAG: cuando llm-service responde consultas, "
        "busca los chunks más similares para enriquecer el prompt enviado a OpenAI."
    ),
    response_description="Chunk indexado con su ID y confirmación.",
    responses={
        502: {"description": "Error de comunicación con Ollama al generar el embedding."},
    },
)
async def index_chunk(
    request: IndexChunkRequest,
    use_case: IndexChunkUseCase = Depends(get_index_chunk_use_case),
):
    return await use_case.execute(request)


@router.post(
    "/chunks/search",
    response_model=SearchResponse,
    summary="Búsqueda semántica por similitud coseno",
    description=(
        "Genera el embedding de la consulta y retorna los `top_k` fragmentos más "
        "similares almacenados, usando la distancia coseno de pgvector (`<=>`). \n\n"
        "Usado internamente por llm-service para construir el contexto RAG antes de "
        "llamar a OpenAI. El score de similitud va de `0.0` (sin relación) a `1.0` (idéntico)."
    ),
    response_description="Lista de chunks ordenados por similitud descendente.",
    responses={
        502: {"description": "Error de comunicación con Ollama al generar el embedding de la consulta."},
    },
)
async def search_chunks(
    request: SearchRequest,
    use_case: SearchChunksUseCase = Depends(get_search_chunks_use_case),
):
    return await use_case.execute(request)
