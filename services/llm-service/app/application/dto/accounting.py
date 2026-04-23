from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ── System Prompts ──────────────────────────────────────────────────────────

class SystemPromptRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Nombre descriptivo del prompt.", examples=["PUC Colombia v2"])
    content: str = Field(
        ...,
        min_length=1,
        description="Instrucciones enviadas al LLM como mensaje de sistema. Debe incluir el formato JSON esperado.",
        examples=["Eres un experto en contabilidad colombiana (PUC). Responde ÚNICAMENTE con JSON válido..."],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "PUC Colombia v2",
                "content": (
                    "Eres un experto en contabilidad colombiana (Plan Único de Cuentas - PUC).\n"
                    "Dado el JSON de una factura electrónica DIAN, genera el asiento contable de causación.\n"
                    "Responde ÚNICAMENTE con JSON válido (sin markdown ni texto adicional) con este formato:\n"
                    "{\"entries\": [{\"cuenta\": \"string\", \"nombre\": \"string\", \"debito\": 0.0, "
                    "\"credito\": 0.0, \"tercero\": \"string|null\", \"centro_costo\": \"string|null\", \"descripcion\": \"string|null\"}]}\n\n"
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
    is_active: bool = Field(..., description="Indica si este prompt es el activo para nuevas generaciones.")
    created_at: datetime = Field(..., description="Fecha y hora de creación.")

    model_config = {"from_attributes": True}


# ── Accounting Entry ────────────────────────────────────────────────────────

class GenerateAccountingRequest(BaseModel):
    document_id: int = Field(..., description="ID del documento (factura) para el cual generar el asiento.", examples=[1])
    top_k: int = Field(default=5, ge=1, le=10, description="Número de chunks similares a recuperar del RAG como contexto (incluye asientos históricos y facturas de referencia).")
    model: str = Field(default="gpt-4o-mini", description="Modelo de OpenAI a utilizar.", examples=["gpt-4o-mini", "gpt-4o"])

    model_config = {
        "json_schema_extra": {
            "example": {"document_id": 1, "top_k": 5, "model": "gpt-4o-mini"}
        }
    }


class EntryLine(BaseModel):
    cuenta: str = Field(..., description="Código de cuenta PUC (Plan Único de Cuentas).", examples=["220500"])
    nombre: str = Field(..., description="Nombre de la cuenta PUC.", examples=["Proveedores nacionales"])
    debito: float = Field(..., description="Valor al débito. Cero si la cuenta va al crédito.", examples=[0.0])
    credito: float = Field(..., description="Valor al crédito. Cero si la cuenta va al débito.", examples=[47900.0])
    tercero: Optional[str] = Field(default=None, description="NIT del tercero relacionado con el movimiento.", examples=["1026288579"])
    centro_costo: Optional[str] = Field(default=None, description="Código del centro de costo. Vacío si no aplica.")
    descripcion: Optional[str] = Field(default=None, description="Descripción del movimiento contable.", examples=["Causación factura FE7674"])


class EntryLineResponse(EntryLine):
    id: int = Field(..., description="Identificador único de la línea.")

    model_config = {"from_attributes": True}


class AccountingEntryResponse(BaseModel):
    id: int = Field(..., description="Identificador único del asiento contable.")
    document_id: int = Field(..., description="ID del documento al que corresponde el asiento.")
    system_prompt_id: Optional[int] = Field(None, description="ID del system prompt utilizado para generar el asiento.")
    lines: List[EntryLineResponse] = Field(default_factory=list, description="Líneas del asiento contable (partida doble), cada una como registro independiente.")
    model_used: Optional[str] = Field(None, description="Modelo de OpenAI que generó el asiento.", examples=["gpt-4o-mini"])
    status: str = Field(..., description="Estado del asiento: `generated` si fue exitoso, `error` si falló.", examples=["generated"])
    error_message: Optional[str] = Field(None, description="Mensaje de error en caso de fallo. Null si el estado es `generated`.")
    rag_context: Optional[List[dict]] = Field(None, description="Chunks RAG usados para inferir la distribución contable (cuentas PUC). No afectan los valores monetarios del asiento.")
    created_at: datetime = Field(..., description="Fecha y hora de generación.")

    model_config = {"from_attributes": True}


# ── Document + Entry (consulta combinada) ──────────────────────────────────

class DocumentWithAccountingResponse(BaseModel):
    document: dict = Field(..., description="Datos completos del documento (factura electrónica DIAN).")
    accounting_entry: Optional[AccountingEntryResponse] = Field(
        None,
        description="Último asiento contable generado para el documento. Null si aún no se ha generado.",
    )


# ── Recalculo batch por rango de fechas ─────────────────────────────────────

class RecalculateAccountingBatchRequest(BaseModel):
    dateini: date = Field(..., description="Fecha de inicio del rango (inclusive). Formato: YYYY-MM-DD.", examples=["2024-01-01"])
    datefin: date = Field(..., description="Fecha de fin del rango (inclusive). Formato: YYYY-MM-DD.", examples=["2024-01-31"])
    status_filter: Optional[str] = Field(
        default=None,
        description="Filtrar documentos por estado antes de recalcular. Ej: `processed`.",
        examples=["processed"],
    )
    top_k: int = Field(default=5, ge=1, le=10, description="Número de chunks RAG por documento.")
    model: str = Field(default="gpt-4o-mini", description="Modelo de OpenAI a utilizar.", examples=["gpt-4o-mini", "gpt-4o"])

    model_config = {
        "json_schema_extra": {
            "example": {
                "dateini": "2024-01-01",
                "datefin": "2024-01-31",
                "status_filter": "processed",
                "top_k": 5,
                "model": "gpt-4o-mini",
            }
        }
    }


class RecalculateAccountingItemResult(BaseModel):
    document_id: int = Field(..., description="ID del documento procesado.")
    document_number: Optional[str] = Field(None, description="Número de la factura (si se conoce).")
    status: str = Field(..., description="Resultado: `generated` si el asiento fue creado o `error` si falló.", examples=["generated", "error"])
    accounting_entry_id: Optional[int] = Field(None, description="ID del asiento contable recién creado. Null si hubo error.")
    error_message: Optional[str] = Field(None, description="Mensaje de error cuando `status` es `error`.")


class RecalculateAccountingBatchResponse(BaseModel):
    dateini: date = Field(..., description="Fecha de inicio del rango procesado.")
    datefin: date = Field(..., description="Fecha de fin del rango procesado.")
    total: int = Field(..., description="Cantidad de documentos encontrados en el rango.")
    generated: int = Field(..., description="Cantidad de asientos generados correctamente.")
    failed: int = Field(..., description="Cantidad de documentos cuyo asiento falló.")
    results: List[RecalculateAccountingItemResult] = Field(
        default_factory=list,
        description="Detalle por documento del resultado del recálculo.",
    )
