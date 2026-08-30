from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

#: Temas admitidos. `proceso` gobierna la decisión completa y entra siempre en el prompt;
#: los demás solo cuando esa retención es candidata para el documento que se está evaluando.
TEMAS = ("retefuente", "reteica", "reteiva", "autorretencion", "proceso")


class RetentionCriterionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tema: str = Field(
        ...,
        description=(
            "Retención a la que aplica el criterio: `retefuente`, `reteica`, `reteiva`, "
            "`autorretencion` o `proceso` (decisión general, aplica siempre)."
        ),
        examples=["reteica"],
        pattern="^(retefuente|reteica|reteiva|autorretencion|proceso)$",
    )
    pregunta: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "Pregunta que originó el criterio. Se conserva porque un criterio suelto pierde "
            "su alcance: «por el municipio» solo significa algo junto a su pregunta."
        ),
        examples=["¿Cómo determinar si una operación está sujeta a ReteICA?"],
    )
    criterio: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Respuesta del contador, tal como la dio.",
        examples=["Por el municipio donde se haya generado la operación."],
    )
    activo: bool = Field(
        default=True,
        description="Permite retirar un criterio sin borrarlo, conservando el rastro.",
    )
    fuente: Optional[str] = Field(
        default=None,
        max_length=200,
        description="De dónde sale el criterio, para poder auditarlo.",
        examples=["Cuestionario respondido por el contador (2026-08-10)"],
    )


class RetentionCriteriaResponse(BaseModel):
    """RF-08: criterios vigentes del tenant.

    Los consume el llm-service **completos**, no por búsqueda semántica: son reglas que
    aplican a todas las facturas, y recuperarlas por parecido las dejaría fuera justo cuando
    el modelo más las necesita, sin que nadie lo notara.
    """

    criterios: list[RetentionCriterionItem] = Field(default_factory=list)
    total: int = Field(..., description="Cantidad de criterios devueltos.", examples=[17])


class RetentionCriteriaReplaceRequest(BaseModel):
    """Reemplaza el conjunto completo de criterios del tenant.

    Se reemplaza en bloque porque el contador revisa sus criterios como un cuerpo único —el
    cuestionario—, no como registros sueltos: editar uno sin ver los demás es como se
    introducen contradicciones entre ellos.
    """

    criterios: list[RetentionCriterionItem] = Field(
        ..., description="Conjunto completo de criterios que queda vigente."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "criterios": [
                    {
                        "tema": "reteica",
                        "pregunta": "¿Cómo determinar si una operación está sujeta a ReteICA?",
                        "criterio": "Por el municipio donde se haya generado la operación.",
                        "activo": True,
                        "fuente": "Confirmado con el contador el 2026-08-10",
                    }
                ]
            }
        }
    }
