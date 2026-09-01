from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.application.dto.tax import TaxResponse


class RetentionResponse(BaseModel):
    id: int = Field(..., description="ID local de la retención.", examples=[10608])
    name: str = Field(
        ...,
        description=(
            "Nombre para mostrar. Para retefuente/reteiva/autorretencion es el que trae "
            "SIIGO o el Excel. Para reteica se sintetiza a partir del municipio y el "
            "concepto (no hay un nombre propio por fila)."
        ),
        examples=["ReteICA Bogotá D.C. · servicios"],
    )
    type: str = Field(
        ...,
        description="Clase normalizada: retefuente | reteica | reteiva | autorretencion.",
        examples=["reteica"],
    )
    percentage: Decimal = Field(
        ...,
        description=(
            "Tarifa. Para reteica va POR MIL (9.66 = 9,66 por mil = 0,966%), igual que la "
            "publican los municipios y como la sincroniza SIIGO; para las demás, porcentaje."
        ),
        examples=["9.660000"],
    )
    active: bool = Field(..., description="Estado de la retención.", examples=[True])
    municipality_code: Optional[str] = Field(
        None,
        description="Código DANE del municipio. Solo presente en filas type='reteica'.",
        examples=["11001"],
    )
    municipality_name: Optional[str] = Field(
        None, description="Nombre del municipio. Solo en reteica.", examples=["Bogotá D.C."]
    )
    retention_concept: Optional[str] = Field(
        None,
        description=(
            "Concepto de la operación que fija la tarifa dentro del municipio "
            "(servicios, compras, honorarios…, o 'todos'). Solo en reteica."
        ),
        examples=["servicios"],
    )
    minimum_base_uvt: Optional[Decimal] = Field(
        None,
        description=(
            "Base mínima en UVT por debajo de la cual no se practica la retención. "
            "Solo tiene sentido en reteica: el ICA es territorial y cada municipio fija "
            "su propio tope."
        ),
        examples=["4.00"],
    )
    source: Optional[str] = Field(
        None,
        description="Origen de la fila: siigo | excel | migracion_integration_taxes | "
        "migracion_retention_ica_rates.",
        examples=["excel"],
    )
    created_at: datetime = Field(..., description="Fecha de creación.")
    updated_at: datetime = Field(..., description="Fecha de última actualización.")

    model_config = {"from_attributes": True}


class ImportRetentionsResponse(BaseModel):
    ica_loaded: int = Field(
        ..., description="Cantidad de tarifas de ReteICA cargadas o actualizadas.", examples=[3]
    )
    retentions: list[RetentionResponse] = Field(
        ..., description="Catálogo de retenciones ReteICA tras la importación."
    )


class SyncSiigoRetentionsResponse(BaseModel):
    """Resultado combinado del sync de `GET /v1/taxes` de SIIGO, repartido por tipo."""

    taxes_imported: int = Field(
        ..., description="Filas de impuesto (IVA/Impoconsumo/AdValorem) sincronizadas.", examples=[5]
    )
    retentions_imported: int = Field(
        ...,
        description="Filas de retención (ReteIVA/Retefuente/Autorretención) sincronizadas.",
        examples=[12],
    )
    reteica_ignored: int = Field(
        ...,
        description=(
            "Filas de tipo ReteICA que SIIGO devolvió y se descartaron: SIIGO no conoce "
            "municipios, así que su ReteICA es un porcentaje plano que no se puede usar. "
            "El ReteICA solo se alimenta de la importación de Excel con municipios "
            "(`POST /api/v1/integrations/retentions/imports`)."
        ),
        examples=[5],
    )
    retentions: list[RetentionResponse] = Field(
        ..., description="Catálogo de retenciones ReteIVA/Retefuente/Autorretención tras el sync."
    )
    taxes: list[TaxResponse] = Field(
        ..., description="Catálogo de impuestos (IVA/Impoconsumo/AdValorem) tras el sync."
    )
