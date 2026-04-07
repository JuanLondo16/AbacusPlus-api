from datetime import datetime
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
                    "Responde ÚNICAMENTE con JSON válido sin texto adicional, con este formato exacto:\n"
                    "{\"entries\": [{\"cuenta\": \"string\", \"nombre\": \"string\", \"debito\": 0.0, "
                    "\"credito\": 0.0, \"tercero\": \"string\", \"centro_costo\": \"string\", \"descripcion\": \"string\"}]}\n"
                    "El total de débitos debe ser igual al total de créditos."
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
    top_k: int = Field(default=3, ge=1, le=10, description="Número de facturas similares a recuperar del RAG como contexto.")
    model: str = Field(default="gpt-4o-mini", description="Modelo de OpenAI a utilizar.", examples=["gpt-4o-mini", "gpt-4o"])

    model_config = {
        "json_schema_extra": {
            "example": {"document_id": 1, "top_k": 3, "model": "gpt-4o-mini"}
        }
    }


class EntryLine(BaseModel):
    cuenta: str = Field(..., description="Código de cuenta PUC (Plan Único de Cuentas).", examples=["220500"])
    nombre: str = Field(..., description="Nombre de la cuenta PUC.", examples=["Proveedores nacionales"])
    debito: float = Field(..., description="Valor al débito. Cero si la cuenta va al crédito.", examples=[0.0])
    credito: float = Field(..., description="Valor al crédito. Cero si la cuenta va al débito.", examples=[47900.0])
    tercero: str = Field(default="", description="NIT del tercero relacionado con el movimiento.", examples=["1026288579"])
    centro_costo: str = Field(default="", description="Código del centro de costo. Vacío si no aplica.")
    descripcion: str = Field(default="", description="Descripción del movimiento contable.", examples=["Causación factura FE7674"])


class AccountingEntryResponse(BaseModel):
    id: int = Field(..., description="Identificador único del asiento contable.")
    document_id: int = Field(..., description="ID del documento al que corresponde el asiento.")
    system_prompt_id: Optional[int] = Field(None, description="ID del system prompt utilizado para generar el asiento.")
    entries: Optional[List[EntryLine]] = Field(None, description="Líneas del asiento contable (partida doble).")
    model_used: Optional[str] = Field(None, description="Modelo de OpenAI que generó el asiento.", examples=["gpt-4o-mini"])
    status: str = Field(..., description="Estado del asiento: `generated` si fue exitoso, `error` si falló.", examples=["generated"])
    error_message: Optional[str] = Field(None, description="Mensaje de error en caso de fallo. Null si el estado es `generated`.")
    created_at: datetime = Field(..., description="Fecha y hora de generación.")

    model_config = {"from_attributes": True}


# ── Document + Entry (consulta combinada) ──────────────────────────────────

class DocumentWithAccountingResponse(BaseModel):
    document: dict = Field(..., description="Datos completos del documento (factura electrónica DIAN).")
    accounting_entry: Optional[AccountingEntryResponse] = Field(
        None,
        description="Último asiento contable generado para el documento. Null si aún no se ha generado.",
    )
