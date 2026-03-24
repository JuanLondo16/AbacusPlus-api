import logging
from app.domain.ports.services import AIServicePort, RagClientPort
from app.application.dto.query import QueryRequest, QueryResponse, ContextChunk

logger = logging.getLogger(__name__)


class QueryWithRAGUseCase:
    def __init__(self, ai_service: AIServicePort, rag_client: RagClientPort):
        self._ai_service = ai_service
        self._rag_client = rag_client

    async def execute(self, request: QueryRequest) -> QueryResponse:
        # 1. Recuperar contexto relevante del rag-service
        chunks = await self._rag_client.search(request.query, top_k=request.top_k)
        logger.info("RAG: %d chunks recuperados para query '%s'", len(chunks), request.query[:60])

        # 2. Construir prompt aumentado con el contexto
        if chunks:
            context_text = "\n\n".join(
                f"[Fragmento {i + 1} — similitud {c['similarity']:.2%}]\n{c['content']}"
                for i, c in enumerate(chunks)
            )
            augmented_prompt = (
                f"Usa el siguiente contexto de facturas DIAN para responder la pregunta.\n\n"
                f"CONTEXTO:\n{context_text}\n\n"
                f"PREGUNTA: {request.query}"
            )
        else:
            augmented_prompt = request.query

        # 3. Llamar a OpenAI con el prompt aumentado
        result = await self._ai_service.complete(augmented_prompt, model=request.model)

        return QueryResponse(
            response=result["content"],
            model=request.model,
            query=request.query,
            context_chunks=[ContextChunk(**c) for c in chunks],
            usage=result["usage"],
        )
