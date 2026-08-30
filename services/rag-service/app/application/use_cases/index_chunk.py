from datetime import datetime

from app.application.dto.chunk import IndexChunkRequest, IndexChunkResponse
from app.domain.entities.chunk import ChunkEntity
from app.domain.ports.repositories import ChunkRepositoryPort
from app.domain.ports.services import EmbeddingServicePort
from app.infrastructure.persistence.models.chunk import EMBEDDING_DIMENSIONS


class IndexChunkUseCase:
    def __init__(self, chunk_repo: ChunkRepositoryPort, embedding_service: EmbeddingServicePort):
        self._chunk_repo = chunk_repo
        self._embedding_service = embedding_service

    async def execute(self, request: IndexChunkRequest) -> IndexChunkResponse:
        # Se embebe la firma del caso cuando quien indexa la envía, y `content` si no.
        #
        # No son el mismo texto y no deben serlo: `content` está escrito para que un modelo lo
        # LEA —con encabezados, rótulos y los datos fijos de la empresa—, y esa plantilla es
        # idéntica en todas las causaciones. Embeberla hace que la similitud mida sobre todo el
        # parecido del formulario: medido sobre el corpus real, cualquier par de causaciones da
        # ~0.94 de similitud coseno, con solo 0.06 separando el propio documento del vecino más
        # cercano. Sobre esa escala, ni el umbral ni el orden significan nada.
        embedding = await self._embedding_service.embed(request.embedding_text or request.content)
        _verificar_dimension(embedding)

        chunk = ChunkEntity(
            source_type=request.source_type,
            source_id=request.source_id,
            content=request.content,
            embedding=embedding,
            is_validated=request.is_validated,
            # La marca de tiempo se pone aquí y no en la base: es el instante en que el
            # documento quedó contabilizado, y sirve para auditar desde cuándo una causación
            # actúa como precedente.
            validated_at=datetime.utcnow() if request.is_validated else None,
            siigo_id=request.siigo_id,
            metadata=request.metadata or {},
        )
        saved = self._chunk_repo.create(chunk)

        return IndexChunkResponse(
            id=saved.id,
            source_type=saved.source_type,
            source_id=saved.source_id,
            is_validated=saved.is_validated,
        )


def _verificar_dimension(embedding) -> None:
    """Falla si el vector no cabe en la columna, en vez de dejar que falle el INSERT.

    El proveedor de embeddings se elige por configuración: OpenAI si hay `OPENAI_API_KEY`
    (1536 dimensiones) y Ollama si no la hay (768). La columna `document_chunks.embedding`
    tiene una dimensión fija, así que arrancar sin la clave produce vectores que la base
    rechaza.

    Eso importa más de lo que parece por dónde ocurre: la indexación del conocimiento de
    RF-08 es **best-effort**, así que el xml-processor se traga el error con un warning y la
    contabilización sigue su curso. El resultado sería un sistema que dice contabilizar
    correctamente y no aprende nada, sin que nadie lo note hasta preguntarse por qué el RAG
    lleva meses vacío. Comprobarlo aquí convierte ese silencio en un mensaje que nombra las
    dos dimensiones y el motivo.
    """
    if embedding is None or len(embedding) != EMBEDDING_DIMENSIONS:
        recibidas = 0 if embedding is None else len(embedding)
        raise ValueError(
            f"El embedding tiene {recibidas} dimensiones y la columna espera "
            f"{EMBEDDING_DIMENSIONS}. Revise el proveedor configurado: sin OPENAI_API_KEY el "
            f"servicio cae a Ollama (768), que no es compatible con la tabla sin migrarla."
        )
