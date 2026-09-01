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

    model_config = {"json_schema_extra": {"example": {"assigned": 3, "skipped": 0, "warnings": []}}}


#: Tope de documentos por lote de asignación. Acota el trabajo que una sola petición puede
#: encargar al modelo: con el semáforo de concurrencia, un lote mayor no va más rápido, solo
#: mantiene la petición abierta más tiempo. Lotes más grandes se parten desde el cliente.
MAX_DOCUMENTOS_POR_LOTE = 200


class CodeAssignmentBatchRequest(BaseModel):
    """Asignación de cuentas PUC para varios documentos en una sola petición."""

    document_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=MAX_DOCUMENTOS_POR_LOTE,
        description=(
            "Documentos a los que asignar cuentas. Los ids repetidos se procesan una sola "
            f"vez. Máximo {MAX_DOCUMENTOS_POR_LOTE} por petición."
        ),
        examples=[[24, 25, 26]],
    )
    model_config = {"json_schema_extra": {"example": {"document_ids": [24, 25, 26]}}}


class CodeAssignmentBatchItem(CodeAssignmentResponse):
    """Resultado de un documento dentro del lote."""

    document_id: int = Field(..., description="Documento al que corresponde.", examples=[24])
    ok: bool = Field(
        ...,
        description=(
            "False si la asignación de ESTE documento falló. El resto del lote continúa: "
            "el motivo queda en `warnings`."
        ),
        examples=[True],
    )


class CodeAssignmentBatchResponse(BaseModel):
    """Resultado agregado y por documento de un lote de asignación."""

    requested: int = Field(..., description="Documentos distintos procesados.", examples=[3])
    succeeded: int = Field(..., description="Documentos sin error.", examples=[3])
    failed: int = Field(..., description="Documentos con error.", examples=[0])
    assigned: int = Field(
        ..., description="Total de líneas actualizadas en todo el lote.", examples=[8]
    )
    results: list[CodeAssignmentBatchItem] = Field(
        ..., description="Detalle por documento, en el orden recibido."
    )


# ── Sugerencia de retenciones (RF-08) ────────────────────────────────────────


class RetentionSuggestion(BaseModel):
    """Una retención propuesta por la IA para el documento.

    El modelo solo decide *cuál* retención aplica. El porcentaje proviene del catálogo de
    impuestos y la base gravable del subtotal del documento, de modo que ningún valor
    tributario depende de la respuesta del modelo.
    """

    tax_id: int = Field(
        ...,
        description="ID de la retención en el catálogo local `integration_taxes`.",
        examples=[3],
    )
    name: str = Field(..., description="Nombre de la retención.", examples=["Retefuente 2.5%"])
    type: str = Field(..., description="Tipo de retención.", examples=["Retefuente"])
    percentage: float = Field(
        ...,
        description="Porcentaje tomado del catálogo de impuestos, no de la respuesta del modelo.",
        examples=[2.5],
    )
    taxable_base: float = Field(
        ...,
        description="Base gravable propuesta: el subtotal del documento. Es ajustable.",
        examples=[148600.0],
    )
    value: float = Field(
        ...,
        description="Valor estimado = base gravable × porcentaje / 100.",
        examples=[3715.0],
    )
    reason: str = Field(
        "",
        description="Justificación breve del modelo sobre por qué aplica esta retención.",
        examples=["Servicio de transporte prestado por persona jurídica"],
    )
    evidence: str = Field(
        "inferencia",
        description=(
            "RF-08 · trazabilidad: qué fuente sustenta la sugerencia. En orden de autoridad: "
            "`tabla_retefuente`, `tabla_reteica`, `perfil_fiscal`, `criterio_contador`, "
            "`caso_historico`, `inferencia`. Permite responder «¿por qué la IA sugirió esto?» "
            "señalando la fuente concreta, no un genérico «lo dijo el modelo»."
        ),
        examples=["tabla_retefuente"],
    )
    confidence: str = Field(
        "media",
        description=(
            "Seguridad de la sugerencia: `alta` si la determina una fuente vinculante "
            "(tabla oficial o perfil fiscal), `media` si se apoyó en criterios o "
            "precedentes, `baja` si hubo que interpretar."
        ),
        examples=["alta"],
    )


class RetentionPersistenceResult(BaseModel):
    """RF-08: resultado de guardar las retenciones determinadas automáticamente."""

    created: int = Field(
        ...,
        description="Retenciones nuevas guardadas en el documento.",
        examples=[2],
    )
    skipped: int = Field(
        ...,
        description=(
            "Retenciones omitidas por estar ya registradas. Reprocesar un documento no "
            "duplica retenciones ni pisa las que el contador registró a mano."
        ),
        examples=[1],
    )


class RetentionSuggestionResponse(BaseModel):
    """RF-08: retenciones propuestas para que el contador confirme o ajuste.

    Llamado desde la interfaz, las sugerencias **no se persisten**: se muestran en la
    sección de retenciones del documento (RF-02) y solo se guardan si el usuario las
    confirma, con lo que la revisión humana sigue siendo obligatoria.

    En la determinación automática (`persist=true`) sí se guardan, porque no hay interfaz
    esperando la respuesta. Quedan marcadas con origen `llm`, de modo que el contador las
    distingue de su propio trabajo y puede ajustarlas o eliminarlas antes de aprobar el
    documento: la revisión humana sigue ocurriendo, solo que sobre datos ya visibles.
    """

    suggestions: list[RetentionSuggestion] = Field(
        default_factory=list,
        description="Retenciones propuestas. Lista vacía si ninguna aplica.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advertencias, por ejemplo si el modelo propuso un impuesto inexistente.",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description=(
            "RF-08: datos que le faltaron al modelo para decidir con certeza (por ejemplo, "
            "que el RUT del proveedor no indique su régimen). Se declaran en vez de "
            "rellenarse con un valor inventado."
        ),
    )
    evidence_used: dict = Field(
        default_factory=dict,
        description=(
            "RF-08 · trazabilidad de la recuperación: qué fuentes se consultaron, con qué "
            "filtros se buscaron los casos contabilizados similares y cuáles se encontraron. "
            "Es lo que permite auditar una sugerencia después de emitida."
        ),
    )
    persisted: Optional[RetentionPersistenceResult] = Field(
        None,
        description=(
            "Solo con `persist=true`: cuántas retenciones se guardaron y cuántas se "
            "omitieron por estar ya registradas en el documento."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "suggestions": [
                    {
                        "tax_id": 3,
                        "name": "Retefuente 2.5%",
                        "type": "Retefuente",
                        "percentage": 2.5,
                        "taxable_base": 148600.0,
                        "value": 3715.0,
                        "reason": "Servicio prestado por persona jurídica declarante",
                        "evidence": "tabla_retefuente",
                        "confidence": "alta",
                    }
                ],
                "warnings": [],
                "missing_information": [],
            }
        }
    }
