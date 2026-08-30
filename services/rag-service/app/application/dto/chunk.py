from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


#: Similitud mínima por defecto para que un chunk pueda considerarse precedente.
#:
#: `search_similar` ordena por distancia y corta en `top_k`, así que SIEMPRE devuelve algo
#: mientras haya chunks: cuando nada se parece, devuelve los menos malos. Esa es la trampa de
#: una búsqueda vectorial sin umbral —no tiene forma de decir «no hay nada»—, y aquí el
#: resultado no es una recomendación mediocre: entra al prompt rotulado como «precedente
#: contable de un caso ya contabilizado», y el modelo lo trata como tal.
#:
#: 0.5 sobre similitud coseno de `text-embedding-3-small` deja pasar el mismo proveedor y el
#: mismo concepto y descarta los pares no relacionados. Es deliberadamente permisivo: el
#: objetivo es cortar el ruido evidente, no afinar el ranking, y un umbral alto de más
#: silencia precedentes buenos, que es el error caro de los dos.
DEFAULT_MIN_SIMILARITY = 0.5


class IndexChunkRequest(BaseModel):
    source_type: str = Field(..., description="Tipo de fuente: 'invoice' | 'file'")
    source_id: Optional[int] = Field(None, description="ID del documento origen")
    content: str = Field(..., min_length=1, description="Texto a indexar")
    is_validated: bool = Field(
        default=False,
        description=(
            "RF-08: marca el chunk como conocimiento contable validado. Solo puede ser True "
            "para una causación efectivamente contabilizada en SIIGO."
        ),
    )
    siigo_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Identificador de la factura en SIIGO que respalda el conocimiento validado.",
    )
    embedding_text: Optional[str] = Field(
        default=None,
        description=(
            "Texto con el que se calcula el embedding, cuando debe ser distinto de `content`.\n\n"
            "`content` es lo que LEE el modelo: lleva encabezados, rótulos y datos fijos que lo "
            "hacen comprensible fuera de contexto. Ese mismo texto, embebido, mide sobre todo "
            "el parecido de la PLANTILLA: dos causaciones de proveedores y conceptos distintos "
            "comparten el 70 % de sus caracteres, y la similitud entre cualquier par del corpus "
            "sale ~0.94. Con esa escala no hay umbral que distinga un precedente de un documento "
            "cualquiera.\n\n"
            "`embedding_text` permite indexar solo lo que distingue un caso de otro —proveedor, "
            "conceptos, cuentas, retenciones— y conservar el texto completo para el prompt. "
            "Si no se envía, se embebe `content`, como siempre."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "RF-08: rasgos estructurados del caso (NIT del emisor, municipio, cuentas, tipos "
            "de retención practicados…). Se usan para filtrar en la búsqueda híbrida."
        ),
    )

    @model_validator(mode="after")
    def _validated_requires_siigo_id(self):
        """RF-08: no hay conocimiento validado sin la prueba de que SIIGO lo aceptó.

        La regla se aplica en el borde del servicio y no solo en quien llama, porque es la
        única forma de garantizar el criterio de aceptación —«una causación aprobada pero no
        contabilizada no aparece como conocimiento del RAG»— para cualquier cliente, actual o
        futuro, del rag-service.
        """
        if self.is_validated and not (self.siigo_id or "").strip():
            raise ValueError(
                "Un chunk validado exige el `siigo_id` de la factura contabilizada: sin él no "
                "consta que la causación superara el envío a SIIGO."
            )
        return self


class InternalIndexChunkRequest(IndexChunkRequest):
    """Variante interna (servicio-a-servicio) del alta de chunk.

    A diferencia de `IndexChunkRequest`, el tenant no se resuelve desde un JWT de usuario
    —el worker de descargas DIAN no tiene sesión de usuario— sino que se recibe explícito.
    Va protegida por `X-Internal-Secret`, mismo patrón que `provision-tenant`.
    """

    tenant_slug: str = Field(..., min_length=1, description="Slug del tenant destino (BD abacus_t_{slug}).")


class InternalRevokeChunkRequest(BaseModel):
    """RF-08: retirada del conocimiento de un documento que dejó de estar contabilizado.

    Una causación contabilizada que después se ajusta o se reversa deja de representar la
    realidad contable, y mantenerla como precedente propagaría el error a los documentos
    siguientes. Por eso la invalidación es un borrado y no un simple `is_validated = False`:
    un texto que ya no describe ningún asiento vigente tampoco sirve como contexto.
    """

    tenant_slug: str = Field(..., min_length=1, description="Slug del tenant destino.")
    source_type: str = Field(default="invoice", description="Tipo de fuente del chunk.")
    source_id: int = Field(..., description="ID del documento cuyo conocimiento se retira.")


class RevokeChunkResponse(BaseModel):
    source_type: str
    source_id: int
    deleted: int
    message: str = "Conocimiento retirado del RAG"


class IndexChunkResponse(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    is_validated: bool = False
    message: str = "Chunk indexado correctamente"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Texto de consulta para búsqueda semántica")
    top_k: int = Field(default=5, ge=1, le=20, description="Número máximo de resultados")
    only_validated: bool = Field(
        default=False,
        description=(
            "RF-08: si es True, solo se devuelven chunks de causaciones contabilizadas en "
            "SIIGO. Es lo que debe usar el llm-service al buscar precedentes contables."
        ),
    )
    min_similarity: float = Field(
        default=DEFAULT_MIN_SIMILARITY,
        ge=0.0,
        le=1.0,
        description=(
            "Similitud coseno mínima (0–1) para devolver un chunk. Por debajo del umbral no "
            "se devuelve nada, en vez de devolver los vecinos menos malos: un resultado sin "
            "parecido real llega al prompt rotulado como precedente y el modelo lo usa como "
            "tal. Con 0.0 se recupera el comportamiento anterior."
        ),
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "RF-08 · búsqueda híbrida: filtros estructurados sobre la metadata del chunk, "
            "aplicados ANTES de ordenar por similitud. El valor puede ser un escalar "
            "(igualdad) o una lista (cualquiera de). Ejemplo: "
            '`{"issuer_nit": "900123456", "retention_types": ["retefuente"]}`.\n\n'
            "Existe porque la similitud semántica no distingue lo que hace comparables dos "
            "facturas: el NIT del proveedor, el municipio o el concepto. Sin filtro, un "
            "vecino textualmente parecido pero de otro tercero desplaza al precedente real."
        ),
    )


class ChunkResult(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    content: str
    similarity: float
    is_validated: bool = False
    siigo_id: Optional[str] = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Rasgos estructurados del caso, para que quien consume pueda citarlos.",
    )


class SearchResponse(BaseModel):
    query: str
    results: list[ChunkResult]
