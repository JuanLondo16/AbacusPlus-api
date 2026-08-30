"""Mapa de códigos de responsabilidad fiscal de la DIAN (RUT) a su significado.

Los códigos viajan en la factura electrónica (`cbc:TaxLevelCode`, lista 48) y determinan si
un tercero es sujeto/agente de retención. Darle al LLM el significado —no solo el código
crudo— mejora la decisión sobre qué retención aplicar.

Solo se incluyen códigos de significado establecido; los no reconocidos se devuelven tal cual
para no inventar interpretaciones.
"""

from typing import Optional

# Fuente: lista de responsabilidades del RUT / anexo técnico de facturación DIAN (lista 48).
DIAN_RESPONSIBILITY_CODES: dict[str, str] = {
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención en el impuesto sobre las ventas (IVA)",
    "O-47": "Régimen simple de tributación (RST)",
    "O-48": "Responsable de IVA",
    "O-49": "No responsable de IVA",
    # Código genérico de persona natural sin responsabilidades específicas relevantes.
    "R-99-PN": "No responsable / sin responsabilidad específica (persona natural)",
}


def describe_code(code: str) -> Optional[str]:
    """Significado de un código de responsabilidad, o None si no se reconoce."""
    return DIAN_RESPONSIBILITY_CODES.get(code.strip().upper())


def expand_responsibilities(raw: Optional[str]) -> list[dict]:
    """Convierte "O-13;O-23" en [{"codigo": "O-13", "significado": "Gran contribuyente"}, ...].

    Los códigos desconocidos se conservan con `significado` en None, para que el modelo vea
    igualmente el código sin que se le atribuya un significado inventado.
    """
    if not raw:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for part in str(raw).split(";"):
        code = part.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"codigo": code, "significado": describe_code(code)})
    return out
