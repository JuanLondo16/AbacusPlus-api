from typing import Optional

from pydantic import BaseModel, Field

from app.domain.value_objects.match_level import MatchLevel


class LookupItem(BaseModel):
    description: str = Field(
        ...,
        description="Descripción del ítem de la factura.",
        examples=["Arriendo oficina mes de mayo"],
    )
    subtotal: float = Field(..., description="Subtotal del ítem.", examples=[1000000.0])
    account: Optional[str] = Field(
        None,
        description="Cuenta PUC asignada al concepto en el catálogo (si existe).",
        examples=["513035"],
    )


class LookupRequest(BaseModel):
    issuer_nit: str = Field(
        ...,
        description="NIT del emisor de la factura.",
        examples=["900123456"],
    )
    items: list[LookupItem] = Field(
        ...,
        description="Ítems del documento para los cuales se busca causación histórica.",
    )
    document_id: Optional[int] = Field(
        None,
        description="ID del documento. Si se provee, se registra el lookup en `rule_match_attempts`.",
        examples=[42],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "issuer_nit": "900123456",
                "document_id": 42,
                "items": [{"description": "Servicio de consultoría", "subtotal": 500000.0}],
            }
        }
    }


class SuggestedEntry(BaseModel):
    debit_account: str = Field(..., description="Cuenta PUC débito sugerida.", examples=["513035"])
    credit_account: str = Field(
        ..., description="Cuenta PUC crédito sugerida.", examples=["220501"]
    )
    tax_accounts: dict = Field(
        default_factory=dict,
        description="Cuentas de impuestos (IVA, retenciones).",
        examples=[{"iva_descontable": "240810", "retefuente": "236540"}],
    )
    cost_center: Optional[str] = Field(
        None, description="Centro de costo sugerido.", examples=["CC001"]
    )


class LookupResponse(BaseModel):
    match_level: MatchLevel = Field(
        ...,
        description="Nivel de coincidencia: `HIT` (confianza ≥ 0.85), `PARTIAL` (0.50–0.84), `MISS` (< 0.50).",
        examples=["HIT"],
    )
    confidence: float = Field(
        ...,
        description="Puntuación de confianza de la regla aplicada (0.0–1.0).",
        examples=[0.90],
    )
    suggested_entry: Optional[SuggestedEntry] = Field(
        None,
        description="Causación sugerida. Presente en HIT y PARTIAL; null en MISS.",
    )
    known_fields: list[str] = Field(
        default_factory=list,
        description="Campos resueltos con confianza (útil en PARTIAL). Ej: ['debit_account', 'cost_center'].",
        examples=[["debit_account"]],
    )
    explanation: str = Field(
        ...,
        description="Descripción del nivel de coincidencia y la regla aplicada.",
        examples=["HIT por NIT+semántica (similitud=0.92). Regla id=7, 5 aprobaciones previas."],
    )
    rule_id: Optional[int] = Field(
        None, description="ID de la regla que generó la respuesta (si aplica)."
    )
    match_key_type: Optional[str] = Field(None, description="Tipo de clave de matching usado.")
