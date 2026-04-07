import json
import logging
from typing import Optional

from fastapi import HTTPException, status

from app.application.dto.accounting import GenerateAccountingRequest, AccountingEntryResponse
from app.domain.ports.services import AIServicePort, RagClientPort
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.persistence.models.accounting_entry import AccountingEntry
from app.infrastructure.persistence.repositories.accounting_repository import AccountingRepository
from app.infrastructure.persistence.repositories.system_prompt_repository import SystemPromptRepository

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "Eres un experto en contabilidad colombiana (Plan Único de Cuentas - PUC).\n"
    "Dado el JSON de una factura electrónica DIAN, genera el asiento contable de causación.\n"
    "Responde ÚNICAMENTE con JSON válido sin texto adicional, con este formato exacto:\n"
    "{\"entries\": [{\"cuenta\": \"string\", \"nombre\": \"string\", "
    "\"debito\": 0.0, \"credito\": 0.0, \"tercero\": \"string\", "
    "\"centro_costo\": \"string\", \"descripcion\": \"string\"}]}\n"
    "El total de débitos debe ser igual al total de créditos."
)


class GenerateAccountingEntryUseCase:
    def __init__(
        self,
        ai_service: AIServicePort,
        rag_client: RagClientPort,
        document_client: DocumentClient,
        accounting_repo: AccountingRepository,
        system_prompt_repo: SystemPromptRepository,
    ):
        self._ai = ai_service
        self._rag = rag_client
        self._doc_client = document_client
        self._accounting_repo = accounting_repo
        self._prompt_repo = system_prompt_repo

    async def execute(self, request: GenerateAccountingRequest) -> AccountingEntryResponse:
        # 1. Obtener documento
        document = await self._doc_client.get_document(request.document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Documento {request.document_id} no encontrado en xml-processor.",
            )

        # 2. Obtener system prompt activo
        active_prompt = self._prompt_repo.get_active()
        system_prompt_text = active_prompt.content if active_prompt else _DEFAULT_SYSTEM_PROMPT
        system_prompt_id = active_prompt.id if active_prompt else None

        # 3. Buscar facturas similares en RAG como referencia
        query_for_rag = (
            f"Factura {document.get('document_number', '')} "
            f"emisor {document.get('issuer_name', '')} "
            f"total {document.get('total', '')}"
        )
        rag_chunks = await self._rag.search(query_for_rag, top_k=request.top_k)
        logger.info(
            "RAG: %d chunks recuperados para causación doc_id=%d",
            len(rag_chunks), request.document_id
        )

        # 4. Construir prompt de usuario
        doc_json = json.dumps(document, ensure_ascii=False, default=str, indent=2)

        rag_context = ""
        if rag_chunks:
            refs = "\n\n".join(
                f"[Ref {i+1} — similitud {c['similarity']:.2%}]\n{c['content']}"
                for i, c in enumerate(rag_chunks)
            )
            rag_context = f"FACTURAS DE REFERENCIA (usa para inferir cuentas PUC):\n{refs}\n\n"

        user_prompt = (
            f"{rag_context}"
            f"FACTURA A CAUSAR (JSON):\n{doc_json}\n\n"
            f"Genera el asiento contable de causación para la factura anterior."
        )

        # 5. Llamar al LLM
        try:
            result = await self._ai.complete(
                prompt=user_prompt,
                model=request.model,
                system_prompt=system_prompt_text,
            )
            raw_response = result["content"]

            # 6. Parsear JSON de la respuesta
            parsed = self._parse_entries(raw_response)

            entry = AccountingEntry(
                document_id=request.document_id,
                system_prompt_id=system_prompt_id,
                entries=parsed,
                model_used=request.model,
                status="generated",
            )
        except Exception as e:
            logger.error("Error generando causación para doc_id=%d: %s", request.document_id, e)
            entry = AccountingEntry(
                document_id=request.document_id,
                system_prompt_id=system_prompt_id,
                model_used=request.model,
                status="error",
                error_message=str(e),
            )

        saved = self._accounting_repo.create(entry)
        return AccountingEntryResponse.model_validate(saved)

    def _parse_entries(self, raw: str) -> list:
        """Extrae el JSON de la respuesta del LLM, tolerando texto extra."""
        text = raw.strip()
        # Buscar el primer { y el último }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"La respuesta del LLM no contiene JSON válido: {text[:200]}")
        data = json.loads(text[start:end])
        return data.get("entries", [])
