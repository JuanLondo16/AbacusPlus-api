from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ── System Prompts ──────────────────────────────────────────────────────────


class SystemPromptRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nombre descriptivo del prompt.",
        examples=["PUC Colombia v2"],
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Instrucciones enviadas al LLM como mensaje de sistema. Debe incluir el formato JSON esperado.",
        examples=[
            "Eres un experto en contabilidad colombiana (PUC). Responde ÚNICAMENTE con JSON válido..."
        ],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "PUC Colombia v2",
                "content": (
                    "Eres un experto en contabilidad colombiana (Plan Único de Cuentas - PUC).\n"
                    "Dado el JSON de una factura electrónica DIAN, genera el asiento contable de causación.\n"
                    "Responde ÚNICAMENTE con JSON válido (sin markdown ni texto adicional) con este formato:\n"
                    '{"entries": [{"cuenta": "string", "nombre": "string", "debito": 0.0, '
                    '"credito": 0.0, "tercero": "string|null", "centro_costo": "string|null", "descripcion": "string|null"}]}\n\n'
                    "Reglas obligatorias:\n"
                    "- Partida doble: suma(debito) = suma(credito).\n"
                    "- Cada línea debe tener debito>0 y credito=0, o credito>0 y debito=0 (nunca ambos >0).\n"
                    "- Montos con máximo 2 decimales.\n"
                    "- Usa el RAG SOLO para inferir distribución contable (cuentas/CC/tercero), no para copiar valores.\n"
                    "- Usa valores monetarios únicamente desde el JSON de la factura.\n"
                ),
            }
        }
    }


class SystemPromptResponse(BaseModel):
    id: int = Field(..., description="Identificador único del prompt.")
    name: str = Field(..., description="Nombre descriptivo del prompt.")
    content: str = Field(..., description="Instrucciones enviadas al LLM como mensaje de sistema.")
    is_active: bool = Field(
        ..., description="Indica si este prompt es el activo para nuevas generaciones."
    )
    created_at: datetime = Field(..., description="Fecha y hora de creación.")

    model_config = {"from_attributes": True}


class SystemPromptActivateRequest(BaseModel):
    """Body para PATCH /accounting/system-prompts/{id}."""

    is_active: bool = Field(
        True, description="Activar (true) este system prompt y desactivar los demás."
    )

    model_config = {"json_schema_extra": {"example": {"is_active": True}}}


# ── Asignación de cuentas PUC ────────────────────────────────────────────────


class CodeAssignmentResponse(BaseModel):
    """Resultado de la asignación de cuentas PUC a las líneas de un documento."""

    assigned: int = Field(
        ...,
        description="Cantidad de líneas de detalle actualizadas con cuenta PUC.",
        examples=[3],
    )
    skipped: int = Field(
        ...,
        description="Cantidad de líneas omitidas (código inválido, detail_id inexistente, etc.).",
        examples=[0],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Lista de advertencias generadas durante la asignación.",
    )

    model_config = {
        "json_schema_extra": {"example": {"assigned": 3, "skipped": 0, "warnings": []}}
    }
