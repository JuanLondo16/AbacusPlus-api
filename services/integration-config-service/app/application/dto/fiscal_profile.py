from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FiscalProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agente_retencion_renta: bool = Field(
        ..., description="La empresa es agente de retención en la fuente (renta / ReteFuente)."
    )
    agente_retencion_ica: bool = Field(..., description="La empresa es agente de retención de ICA.")
    agente_retencion_iva: bool = Field(
        ..., description="La empresa es agente de retención de IVA (ReteIVA)."
    )
    autorretenedor_renta: bool = Field(..., description="La empresa es autorretenedora de renta.")
    gran_contribuyente: bool = Field(..., description="La empresa es Gran Contribuyente.")
    responsable_iva: bool = Field(..., description="La empresa es responsable de IVA.")
    regimen: str = Field(..., description="Régimen tributario: 'ordinario' o 'simple' (RST).")
    notas: Optional[str] = Field(None, description="Notas del contador sobre el perfil.")


class FiscalProfileUpsertRequest(BaseModel):
    agente_retencion_renta: bool = False
    agente_retencion_ica: bool = False
    agente_retencion_iva: bool = False
    autorretenedor_renta: bool = False
    gran_contribuyente: bool = False
    responsable_iva: bool = False
    regimen: str = Field(
        default="ordinario",
        description="Régimen tributario: 'ordinario' o 'simple'.",
        pattern="^(ordinario|simple)$",
    )
    notas: Optional[str] = Field(default=None, max_length=500)

    model_config = {
        "json_schema_extra": {
            "example": {
                "agente_retencion_renta": True,
                "agente_retencion_ica": True,
                "agente_retencion_iva": False,
                "autorretenedor_renta": False,
                "gran_contribuyente": True,
                "responsable_iva": True,
                "regimen": "ordinario",
                "notas": "Confirmado con el contador el 2026-08-09.",
            }
        }
    }
