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

        # Separar chunks por tipo
        historical_chunks = [c for c in rag_chunks if c.get("source_type") == "historical_entry"]
        generated_chunks  = [c for c in rag_chunks if c.get("source_type") == "generated_entry"]
        invoice_chunks    = [c for c in rag_chunks if c.get("source_type") == "invoice"]

        rag_prompt = ""
        # IMPORTANTE: el RAG se usa SOLO para inferir la distribución contable (cuentas PUC,
        # débitos/créditos, centros de costo). Los valores monetarios vienen exclusivamente
        # del JSON de la factura a causar.
        if historical_chunks:
            hist_refs = "\n\n".join(
                f"[Asiento histórico {i+1} — similitud {c['similarity']:.2%}]\n{c['content']}"
                for i, c in enumerate(historical_chunks)
            )
            rag_prompt += (
                "ASIENTOS HISTÓRICOS DE REFERENCIA (Odoo)\n"
                "(usa SOLO para inferir qué cuentas PUC, débitos/créditos y centros de costo aplicar —\n"
                " los valores monetarios debes tomarlos del JSON de la factura):\n"
                f"{hist_refs}\n\n"
            )

        if generated_chunks:
            gen_refs = "\n\n".join(
                f"[Causación previa {i+1} — similitud {c['similarity']:.2%}]\n{c['content']}"
                for i, c in enumerate(generated_chunks)
            )
            rag_prompt += (
                "CAUSACIONES PREVIAS DEL SISTEMA\n"
                "(asientos generados anteriormente para facturas similares —\n"
                " usa SOLO para inferir la distribución contable, no los valores):\n"
                f"{gen_refs}\n\n"
            )

        if invoice_chunks:
            inv_refs = "\n\n".join(
                f"[Ref {i+1} — similitud {c['similarity']:.2%}]\n{c['content']}"
                for i, c in enumerate(invoice_chunks)
            )
            rag_prompt += (
                "FACTURAS DE REFERENCIA\n"
                "(usa SOLO para inferir la distribución contable, no los valores):\n"
                f"{inv_refs}\n\n"
            )

        user_prompt = (
            f"{rag_prompt}"
            f"FACTURA A CAUSAR (JSON):\n{doc_json}\n\n"
            f"Genera el asiento contable de causación para la factura anterior. "
            f"Usa los valores monetarios del JSON de la factura, no los de las referencias."
        )

        # Snapshot del contexto RAG para auditoría (qué fuentes se usaron y su similitud)
        rag_context_snapshot = [
            {
                "source_type": c.get("source_type"),
                "source_id": c.get("source_id"),
                "similarity": c.get("similarity"),
                "content": c.get("content"),
            }
            for c in rag_chunks
        ]

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
                model_used=request.model,
                status="generated",
                rag_context=rag_context_snapshot,
            )
            saved = self._accounting_repo.create(entry, lines_data=parsed)

            # Indexar el asiento generado en RAG para que futuras causaciones lo usen como referencia
            chunk_content = self._build_entry_chunk(document, saved, parsed)
            await self._rag.index_chunk(
                source_type="generated_entry",
                source_id=saved.id,
                content=chunk_content,
            )
        except Exception as e:
            logger.error("Error generando causación para doc_id=%d: %s", request.document_id, e)
            entry = AccountingEntry(
                document_id=request.document_id,
                system_prompt_id=system_prompt_id,
                model_used=request.model,
                status="error",
                error_message=str(e),
                rag_context=rag_context_snapshot,
            )
            saved = self._accounting_repo.create(entry, lines_data=[])

        return AccountingEntryResponse.model_validate(saved)

    def _build_entry_chunk(self, document: dict, entry, lines: list) -> str:
        """Construye el texto a indexar en RAG para una causación generada por el sistema."""
        header = (
            f"Causación {document.get('document_number', '')} | "
            f"Fecha: {document.get('date', '')} | "
            f"Emisor: {document.get('issuer_name', '')} NIT {document.get('issuer_nit', '')} | "
            f"Total: {document.get('total', '')}"
        )
        line_texts = "\n".join(
            f"  {l.get('cuenta', '')} {l.get('nombre', '')} | "
            f"Débito: {l.get('debito', 0)} | Crédito: {l.get('credito', 0)} | "
            f"CC: {l.get('centro_costo', '') or ''} | Desc: {l.get('descripcion', '') or ''}"
            for l in lines
        )
        return f"{header}\nLíneas contables:\n{line_texts}"

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
