from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.chunk import (
    IndexChunkRequest,
    IndexChunkResponse,
    SearchRequest,
    SearchResponse,
)
from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase
from app.dependencies import get_index_chunk_use_case, get_search_chunks_use_case
from app.infrastructure.config.auth_dependency import require_write

router = APIRouter()


@router.post(
    "/chunks",
    dependencies=[Depends(require_write)],
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
    # RF-08: el conocimiento contable validado no entra por aquí. Marcar un chunk como
    # validado exige constar que el documento quedó CONTABILIZADO en SIIGO, y eso solo lo
    # sabe el xml-processor al cerrar la contabilización; esta ruta la usa cualquier cliente
    # con un token de usuario, que no puede aportar esa garantía. La vía es
    # `POST /internal/chunks` con `X-Internal-Secret`.
    if request.is_validated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "El conocimiento contable validado solo puede crearlo el proceso de "
                "contabilización, al confirmarse el estado «Contabilizada» en SIIGO."
            ),
        )
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
        502: {
            "description": "Error de comunicación con Ollama al generar el embedding de la consulta."
        },
    },
)
async def search_chunks(
    request: SearchRequest,
    use_case: SearchChunksUseCase = Depends(get_search_chunks_use_case),
):
    return await use_case.execute(request)
