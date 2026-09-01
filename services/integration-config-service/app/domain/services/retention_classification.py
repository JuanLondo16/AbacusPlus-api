"""Clasificación tributaria de una fila que SIIGO llama "impuesto" (`GET /v1/taxes`).

SIIGO mezcla en un solo endpoint impuestos reales del documento (IVA, Impoconsumo,
AdValorem) y retenciones (Retefuente, ReteICA, ReteIVA, Autorretención), distinguidos solo
por `type`. Este servicio ahora reparte esa respuesta en dos tablas físicas
(`integration_taxes` para impuestos, `integration_retentions` para retenciones), así que
necesita saber, fila a fila, a cuál pertenece cada una.

Es una clasificación PROPIA de este servicio, independiente de la que ya existe en
`llm-service/app/domain/services/tax_catalog.py` — el proyecto no comparte código entre
microservicios ("Dominio independiente: las entidades de dominio no se comparten entre
servicios"), y el propósito aquí es más acotado: solo enrutar una fila a la tabla correcta,
no decidir qué es "practicable en una compra" ni deduplicar filas gemelas (eso lo sigue
haciendo el llm-service sobre lo que ya está separado).
"""

import unicodedata
from typing import Any

#: Tipos de retención que este servicio separa de los impuestos. Nomenclatura interna en
#: minúsculas; el valor guardado en `type` conserva la grafía original de SIIGO/Excel
#: ("Retefuente", "ReteICA"...), igual que ya hace `integration_taxes.type` hoy.
RETENTION_TYPES = frozenset({"retefuente", "reteica", "reteiva", "autorretencion"})

#: Tipos de impuesto real del documento. Se listan para dejar constancia explícita de qué se
#: reconoce como impuesto y detectar tipos nuevos que ni sean impuesto ni retención conocida
#: (se clasifican como "" y se registran, nunca se adivinan).
TAX_TYPES = frozenset({"iva", "impoconsumo", "advalorem"})


def _normalize(value: Any) -> str:
    """Minúsculas, sin tildes, sin espacios ni puntuación — igual criterio que el resto del
    proyecto usa para comparar tipos que SIIGO o un Excel pueden escribir de varias formas."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c for c in text.lower() if c.isalnum())


def classify(type_or_name: Any) -> str:
    """Clase tributaria normalizada: 'retefuente' | 'reteica' | 'reteiva' | 'autorretencion'
    | 'iva' | 'impoconsumo' | 'advalorem' | '' (desconocida, nunca se adivina).

    Se compara por subcadena y no por igualdad exacta porque el `type` real trae variantes:
    "Retefuente", "ReteFuente", "RETEFUENTE". El orden importa: "autorretencion" CONTIENE
    "retencion", así que se comprueba antes que retefuente/reteiva/reteica para no
    clasificar mal una autorretención.
    """
    texto = _normalize(type_or_name)
    if not texto:
        return ""
    if "autorreten" in texto:
        return "autorretencion"
    if "reteiva" in texto:
        return "reteiva"
    if "reteica" in texto:
        return "reteica"
    if "retefuente" in texto or "retefte" in texto:
        return "retefuente"
    if "impoconsumo" in texto or texto == "inc":
        return "impoconsumo"
    if "advalorem" in texto:
        return "advalorem"
    if "iva" in texto:
        return "iva"
    return ""


def is_retention(type_or_name: Any) -> bool:
    return classify(type_or_name) in RETENTION_TYPES


def is_tax(type_or_name: Any) -> bool:
    return classify(type_or_name) in TAX_TYPES
