import json
import logging
import math
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
    "Responde ÚNICAMENTE con JSON válido (sin markdown ni texto adicional) con este formato:\n"
    "{\"entries\": [{\"cuenta\": \"string\", \"nombre\": \"string\", "
    "\"debito\": 0.0, \"credito\": 0.0, \"tercero\": \"string|null\", "
    "\"centro_costo\": \"string|null\", \"descripcion\": \"string|null\"}]}\n\n"
    "Reglas obligatorias:\n"
    "- Partida doble: suma(debito) = suma(credito).\n"
    "- Cada línea debe tener debito>0 y credito=0, o credito>0 y debito=0 (nunca ambos >0).\n"
    "- Montos con máximo 2 decimales.\n"
    "- Usa el RAG SOLO para inferir distribución contable (cuentas/CC/tercero), no para copiar valores.\n"
    "- Usa valores monetarios únicamente desde el JSON de la factura.\n"
)

_ACCOUNTING_JSON_SCHEMA = {
    "name": "accounting_entry",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["entries"],
        "properties": {
            "entries": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["cuenta", "nombre", "debito", "credito"],
                    "properties": {
                        "cuenta": {"type": "string", "minLength": 1, "maxLength": 20},
                        "nombre": {"type": "string", "minLength": 1, "maxLength": 200},
                        "debito": {"type": "number", "minimum": 0},
                        "credito": {"type": "number", "minimum": 0},
                        "tercero": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "centro_costo": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "descripcion": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                },
            }
        },
    },
}


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
        # Evitar feedback loop: solo usa asientos generados si la similitud es realmente alta.
        generated_chunks = [
            c for c in rag_chunks
            if c.get("source_type") == "generated_entry" and float(c.get("similarity") or 0) >= 0.92
        ]
        invoice_chunks = [c for c in rag_chunks if c.get("source_type") == "invoice"]

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
            f"Usa los valores monetarios del JSON de la factura, no los de las referencias. "
            f"Devuelve únicamente JSON válido con la clave 'entries'."
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
                temperature=0.1,
                json_schema=_ACCOUNTING_JSON_SCHEMA,
            )
            raw_response = result["content"]

            # 6. Parsear JSON de la respuesta
            parsed = self._parse_entries(raw_response)
            parsed = self._normalize_entries(parsed)
            parsed = self._validate_and_repair_entries(parsed)

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
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("La respuesta del LLM no contiene una lista válida en 'entries'.")
        return entries

    def _normalize_entries(self, entries: list) -> list[dict]:
        normalized: list[dict] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            cuenta = str(e.get("cuenta") or "").strip()
            nombre = str(e.get("nombre") or "").strip()
            if not cuenta or not nombre:
                continue
            debito = self._to_money(e.get("debito"))
            credito = self._to_money(e.get("credito"))
            tercero = e.get("tercero")
            centro_costo = e.get("centro_costo")
            descripcion = e.get("descripcion")

            normalized.append(
                {
                    "cuenta": cuenta,
                    "nombre": nombre,
                    "debito": debito,
                    "credito": credito,
                    "tercero": str(tercero).strip() if isinstance(tercero, str) and tercero.strip() else None,
                    "centro_costo": str(centro_costo).strip() if isinstance(centro_costo, str) and centro_costo.strip() else None,
                    "descripcion": str(descripcion).strip() if isinstance(descripcion, str) and descripcion.strip() else None,
                }
            )
        return normalized

    def _validate_and_repair_entries(self, entries: list[dict]) -> list[dict]:
        if len(entries) < 2:
            raise ValueError("El asiento debe contener al menos 2 líneas.")

        repaired: list[dict] = []
        for e in entries:
            d = float(e.get("debito") or 0)
            c = float(e.get("credito") or 0)
            if d < 0 or c < 0:
                raise ValueError("Los montos no pueden ser negativos.")
            if d > 0 and c > 0:
                # regla estricta: dividir en dos líneas no es seguro; mejor fallar
                raise ValueError("Una línea no puede tener débito y crédito simultáneamente.")
            if d == 0 and c == 0:
                continue
            repaired.append(e)

        if len(repaired) < 2:
            raise ValueError("El asiento debe contener al menos 2 líneas con valor.")

        sum_deb = self._to_money(sum(float(e["debito"]) for e in repaired))
        sum_cre = self._to_money(sum(float(e["credito"]) for e in repaired))
        diff = self._to_money(sum_deb - sum_cre)

        # Tolerancia por redondeos: 1 centavo
        if math.isclose(diff, 0.0, abs_tol=0.01):
            return repaired

        # Reparación determinística: agregar línea de ajuste por redondeo.
        # Cuenta configurable por variable de entorno; fallback genérico.
        import os

        adj_account = os.getenv("ACCOUNTING_ADJUSTMENT_ACCOUNT", "539520")
        adj_name = os.getenv("ACCOUNTING_ADJUSTMENT_ACCOUNT_NAME", "Ajuste por redondeo")
        adj_line = {
            "cuenta": adj_account,
            "nombre": adj_name,
            "debito": 0.0,
            "credito": 0.0,
            "tercero": None,
            "centro_costo": None,
            "descripcion": "Ajuste por redondeo (autogenerado)",
        }
        if diff > 0:
            # hay más débito que crédito, falta crédito
            adj_line["credito"] = abs(diff)
        else:
            adj_line["debito"] = abs(diff)
        repaired.append(adj_line)

        # Revalidar
        sum_deb2 = self._to_money(sum(float(e["debito"]) for e in repaired))
        sum_cre2 = self._to_money(sum(float(e["credito"]) for e in repaired))
        if not math.isclose(sum_deb2, sum_cre2, abs_tol=0.01):
            raise ValueError("No fue posible balancear el asiento contable.")
        return repaired

    def _to_money(self, value) -> float:
        try:
            v = float(value)
        except Exception:
            v = 0.0
        # Normalizar a 2 decimales
        return round(v + 1e-12, 2)
