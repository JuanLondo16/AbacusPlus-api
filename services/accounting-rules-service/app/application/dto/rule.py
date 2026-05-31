from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateRuleRequest(BaseModel):
    match_key_type: str = Field(
        ...,
        description="Tipo de clave de matching: `nit_semantic` | `nit_only` | `keyword_only`.",
        examples=["nit_only"],
    )
    issuer_nit: Optional[str] = Field(
        None,
        description="NIT del emisor. Requerido para `nit_semantic` y `nit_only`.",
        examples=["900123456"],
    )
    item_keywords: Optional[list[str]] = Field(
        None,
        description="Palabras clave de descripción del ítem. Requerido para `keyword_only`.",
        examples=[["arriendo", "arrendamiento"]],
    )
    suggested_debit_account: str = Field(
        ...,
        description="Código de cuenta PUC para el débito.",
        examples=["513035"],
    )
    suggested_credit_account: str = Field(
        ...,
        description="Código de cuenta PUC para el crédito.",
        examples=["220501"],
    )
    suggested_tax_accounts: dict = Field(
        default_factory=dict,
        description="Cuentas de impuestos sugeridas (IVA, retenciones) como dict.",
        examples=[{"iva_descontable": "240810", "retefuente": "236540"}],
    )
    suggested_cost_center: Optional[str] = Field(
        None,
        description="Código de centro de costo sugerido.",
        examples=["CC001"],
    )
    confidence_score: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Puntuación de confianza inicial (0.0–1.0).",
        examples=[0.60],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "match_key_type": "nit_only",
                "issuer_nit": "900123456",
                "suggested_debit_account": "513035",
                "suggested_credit_account": "220501",
                "suggested_tax_accounts": {"iva_descontable": "240810"},
                "confidence_score": 0.60,
            }
        }
    }


class RuleResponse(BaseModel):
    id: int = Field(..., description="Identificador único de la regla.")
    match_key_type: str = Field(..., description="Tipo de clave de matching.")
    issuer_nit: Optional[str] = Field(None, description="NIT del emisor.")
    ciiu_code: Optional[str] = Field(None, description="Código CIIU (reservado).")
    item_keywords: Optional[list[str]] = Field(None, description="Palabras clave del ítem.")
    suggested_debit_account: str = Field(..., description="Cuenta PUC débito sugerida.")
    suggested_credit_account: str = Field(..., description="Cuenta PUC crédito sugerida.")
    suggested_tax_accounts: dict = Field(..., description="Cuentas de impuestos sugeridas.")
    suggested_cost_center: Optional[str] = Field(None, description="Centro de costo sugerido.")
    confidence_score: float = Field(..., description="Puntuación de confianza actual.")
    approval_count: int = Field(
        ..., description="Número de aprobaciones que reforzaron esta regla."
    )
    edit_count: int = Field(
        ..., description="Número de veces que se corrigió el asiento antes de aprobar."
    )
    last_approved_at: Optional[datetime] = Field(
        None, description="Última vez que se aprobó con esta regla."
    )
    is_active: bool = Field(..., description="Si la regla está activa.")
    created_at: Optional[datetime] = Field(None, description="Fecha de creación.")
    updated_at: Optional[datetime] = Field(None, description="Última actualización.")


class UpdateRuleRequest(BaseModel):
    is_active: Optional[bool] = Field(
        None,
        description="Activar o desactivar la regla.",
        examples=[True],
    )
    confidence_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Ajuste manual del score de confianza.",
        examples=[0.75],
    )

    model_config = {"json_schema_extra": {"example": {"is_active": False}}}


class RuleStatsResponse(BaseModel):
    total_attempts: int = Field(..., description="Total de lookups realizados.")
    hit_rate: float = Field(..., description="Tasa de HITs sobre total de lookups.")
    partial_rate: float = Field(..., description="Tasa de PARTIALs.")
    miss_rate: float = Field(..., description="Tasa de MISSes.")
    precision: float = Field(
        ...,
        description="Proporción de lookups con contexto (HIT/PARTIAL) que fueron aprobados sin corrección.",
    )
    precision_by_key_type: dict = Field(
        ...,
        description="Conteo de lookups por tipo de clave de matching.",
    )
    total_rules: int = Field(..., description="Total de reglas activas en el sistema.")


class ApprovalLine(BaseModel):
    cuenta: str = Field(..., description="Código de cuenta PUC.", examples=["513035"])
    nombre: Optional[str] = Field(None, description="Nombre de la cuenta.")
    debito: float = Field(..., description="Valor al débito.", examples=[0.0])
    credito: float = Field(..., description="Valor al crédito.", examples=[100000.0])
    tercero: Optional[str] = Field(None, description="NIT del tercero.")
    centro_costo: Optional[str] = Field(None, description="Centro de costo.")
    descripcion: Optional[str] = Field(None, description="Descripción del movimiento.")


class ApprovalItem(BaseModel):
    description: str = Field(
        ..., description="Descripción del ítem de la factura.", examples=["Servicio de consultoría"]
    )
    subtotal: float = Field(..., description="Subtotal del ítem.", examples=[100000.0])
    account: Optional[str] = Field(None, description="Cuenta PUC asignada al concepto.")


class ApprovalNotification(BaseModel):
    document_id: int = Field(..., description="ID del documento aprobado.", examples=[42])
    issuer_nit: str = Field(..., description="NIT del emisor.", examples=["900123456"])
    items: list[ApprovalItem] = Field(..., description="Ítems del documento.")
    approved_lines: list[ApprovalLine] = Field(
        ..., description="Líneas del asiento contable aprobado."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": 42,
                "issuer_nit": "900123456",
                "items": [{"description": "Arriendo oficina", "subtotal": 100000.0}],
                "approved_lines": [
                    {
                        "cuenta": "513035",
                        "nombre": "Arrendamientos",
                        "debito": 100000.0,
                        "credito": 0.0,
                    },
                    {
                        "cuenta": "220501",
                        "nombre": "Proveedores nacionales",
                        "debito": 0.0,
                        "credito": 100000.0,
                    },
                ],
            }
        }
    }
