import logging
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocumentTaxResponse(BaseModel):
    id: int = Field(..., description="ID del registro de impuesto del documento.", examples=[1])
    document_id: int = Field(..., description="ID del documento al que pertenece.", examples=[10])
    tax_id: int = Field(
        ...,
        description="ID del impuesto/retención en el catálogo local `integration_taxes`.",
        examples=[3],
    )
    taxable_base: float = Field(
        0.0,
        description="RF-02: base gravable sobre la que se calcula la retención.",
        examples=[100000.0],
    )
    percentage: float = Field(
        0.0,
        description="RF-02: porcentaje aplicado de la retención (ej. 2.5 = 2.5%).",
        examples=[2.5],
    )
    value: float = Field(
        ...,
        description=(
            "Valor retenido. Se calcula en el servidor: base gravable × tarifa / 100, "
            "o / 1000 en ReteICA, cuya tarifa los municipios publican por mil."
        ),
        examples=[2500.0],
    )
    source: Optional[str] = Field(
        None,
        description=(
            "RF-08: origen de la retención. `llm` si nació de una sugerencia aceptada, "
            "`manual` si la agregó el contador. La interfaz lo usa para advertir antes de "
            "regenerar sugerencias sobre retenciones registradas manualmente."
        ),
        examples=["manual"],
    )

    model_config = {"from_attributes": True}


#: Unidad en la que cada tipo de impuesto publica su tarifa.
#:
#: Se declara tipo por tipo, sin dejar ninguno al criterio de un valor por defecto: la misma
#: cifra —7,66— significa dos cosas distintas según la unidad, y se diferencian en un factor
#: de diez sobre dinero de un tercero. Un mapa explícito obliga a decidirlo cuando aparece un
#: tipo nuevo, en lugar de heredar silenciosamente el divisor de otro.
#:
#: La unidad de cada uno está contrastada con el catálogo real de la empresa:
#:
#: - **ReteICA — por mil.** Los municipios publican el ICA por mil (Bogotá servicios 9,66 por
#:   mil) y SIIGO sincroniza esa cifra tal cual. Las tarifas del catálogo van de 4,14 a 13,80:
#:   leerlas como porcentaje daría un ICA del 13,8 %, que no existe.
#: - **Retefuente — porcentaje.** Sus tarifas (1; 2,5; 3,5; 4; 6; 7; 10; 11) son las de la
#:   retención en la fuente tal como las fija la DIAN.
#: - **ReteIVA — porcentaje.** El 15 % del IVA facturado.
#: - **IVA, Impoconsumo — porcentaje.** 0, 5 y 19 el primero; 8 el segundo.
#: - **Autorretención — porcentaje.** La del catálogo es de renta (1,10 %). Si alguna vez se
#:   sincroniza una autorretención de *ICA*, será por mil y habrá que distinguirla aquí: el
#:   tipo por sí solo dejará de bastar.
#:
#: Se comprobó contra el ambiente real: sobre una base de 110.554,62 con ReteICA 7,66, Abacus
#: registraba 8.468,48 mientras SIIGO practicaba 846,85 —que es 7,66/1000—. La ReteIVA del
#: mismo documento coincidía al céntimo, porque su tarifa sí es un porcentaje.
POR_CIENTO = Decimal(100)
POR_MIL = Decimal(1000)

_UNIDAD_POR_TIPO: dict[str, Decimal] = {
    "reteica": POR_MIL,
    "retefuente": POR_CIENTO,
    "reteiva": POR_CIENTO,
    "autorretencion": POR_CIENTO,
    "iva": POR_CIENTO,
    "impoconsumo": POR_CIENTO,
}


def divisor_de_la_tarifa(tax_type: Optional[str]) -> Decimal:
    """Divisor que convierte la tarifa del catálogo en una fracción.

    Ante un tipo no declarado se asume porcentaje —es la unidad de cinco de los seis tipos
    conocidos— y se deja constancia: un tipo nuevo cuya tarifa fuera por mil retendría diez
    veces de más, y ese fallo no se manifiesta como un error sino como una cifra plausible.
    """
    clave = _normalizar_tipo(tax_type)
    divisor = _UNIDAD_POR_TIPO.get(clave)
    if divisor is not None:
        return divisor
    if clave:
        logger.warning(
            "RF-02: el tipo de impuesto %r no tiene una unidad declarada; se aplica "
            "porcentaje. Si su tarifa se publica por mil, la retención saldría diez veces "
            "mayor: decláralo en `_UNIDAD_POR_TIPO`.",
            tax_type,
        )
    return POR_CIENTO


def _normalizar_tipo(tax_type: Optional[str]) -> str:
    """El tipo tal y como se compara: sin tildes, espacios ni mayúsculas.

    El catálogo escribe «Autorretencion» y «autorretención.» para el mismo concepto, así que
    comparar la cadena literal dejaría fuera a una de las dos.
    """
    sin_tildes = "".join(
        c
        for c in unicodedata.normalize("NFD", str(tax_type or ""))
        if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.strip().strip(".").strip().lower()


def compute_retention_value(
    taxable_base: float, percentage: float, tax_type: Optional[str] = None
) -> float:
    """Valor retenido = base gravable × tarifa / divisor, redondeado a 2 decimales.

    El divisor depende del tipo: 1000 para ReteICA, que se publica por mil, y 100 para el
    resto. `tax_type` es opcional para no romper a quien ya llamaba con dos argumentos; sin
    él se asume porcentaje, que es el comportamiento anterior.

    El cálculo se hace en `Decimal` y no en coma flotante, y redondea HALF_UP en lugar de
    usar `round()`. Las dos cosas responden a errores concretos, no a purismo:

    - `round()` de Python aplica redondeo **bancario** (al par más cercano), de modo que
      `round(314.715, 2)` devuelve 314.71 y no 314.72. Sobre una retención eso es un centavo
      de menos, siempre en la misma dirección, en todos los documentos que caigan en el medio
      exacto. La práctica tributaria colombiana redondea hacia arriba en ese punto.

    - La conversión pasa por `str()` a propósito. `Decimal(0.1)` arrastra el error binario del
      flotante (0.1000000000000000055…), mientras que `Decimal(str(0.1))` recupera el valor
      decimal que el XML declaró, que es el que tiene validez.

    Se mantiene `float` en la firma porque es el tipo que usan los modelos y los DTO; lo que
    cambia es que la aritmética intermedia deja de ser binaria.
    """
    base = Decimal(str(taxable_base or 0))
    pct = Decimal(str(percentage or 0))
    divisor = divisor_de_la_tarifa(tax_type)
    valor = (base * pct / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(valor)


class DocumentTaxCreateRequest(BaseModel):
    tax_id: int = Field(
        ...,
        description="ID del impuesto/retención en el catálogo local `integration_taxes`.",
        examples=[3],
    )
    taxable_base: float = Field(
        ...,
        ge=0,
        description="RF-02: base gravable de la retención. El valor retenido se calcula en el servidor.",
        examples=[100000.0],
    )
    percentage: float = Field(
        ...,
        ge=0,
        le=100,
        description="RF-02: porcentaje de la retención (0–100).",
        examples=[2.5],
    )

    source: Optional[str] = Field(
        "manual",
        description=(
            "RF-08: `llm` cuando la interfaz confirma una sugerencia del modelo, `manual` "
            "en el alta desde el formulario. Es una etiqueta de procedencia para poder "
            "advertir antes de regenerar sugerencias; no altera ningún cálculo."
        ),
        examples=["manual"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "tax_id": 3,
                "taxable_base": 100000.0,
                "percentage": 2.5,
                "source": "manual",
            }
        }
    }


class DocumentTaxSuggestionResponse(BaseModel):
    """Resultado de persistir las retenciones que la IA determinó automáticamente (RF-08)."""

    created: int = Field(
        ...,
        description="Retenciones nuevas guardadas en el documento.",
        examples=[2],
    )
    skipped: int = Field(
        ...,
        description=(
            "Retenciones omitidas por estar ya registradas en el documento. El "
            "reprocesamiento de un XML no duplica lo que el contador ya tiene."
        ),
        examples=[1],
    )

    model_config = {"json_schema_extra": {"example": {"created": 2, "skipped": 1}}}


class DocumentTaxUpdateRequest(BaseModel):
    tax_id: Optional[int] = Field(
        None, description="Nuevo ID de impuesto. Si se omite, no se modifica.", examples=[3]
    )
    taxable_base: Optional[float] = Field(
        None,
        ge=0,
        description="Nueva base gravable. Si se omite, no se modifica.",
        examples=[120000.0],
    )
    percentage: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Nuevo porcentaje. Si se omite, no se modifica.",
        examples=[3.5],
    )

    model_config = {"json_schema_extra": {"example": {"taxable_base": 120000.0, "percentage": 3.5}}}
