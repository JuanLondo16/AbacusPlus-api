"""Las retenciones que el proveedor declara en el XML de la DIAN.

Vienen en `cac:WithholdingTaxTotal`, aparte de los impuestos. El parser ya las extraía, pero
al guardar el documento se sumaban en dos columnas —`documents.retefuente` y
`documents.reteica`— que **no se leen en ningún punto del sistema**, y el esquema 08 (ReteIVA)
se descartaba entero.

Qué son y qué no son
--------------------
**No son la fuente de verdad.** En una factura de compra estas retenciones son las que el
*proveedor* declara esperar, no necesariamente las que la empresa debe practicar. Quien decide
es el perfil fiscal del comprador y la configuración del tercero en SIIGO.

Son la **única señal independiente** para contrastar lo que Abacus determina. Eso importa
porque SIIGO no informa qué retenciones practicó: `PurchasesOut` no trae ningún campo
`retentions`, así que lo único observable del comprobante es su total. Sin esta señal, no hay
segundo par de ojos sobre la decisión.

Las unidades no coinciden entre las dos puntas
-----------------------------------------------
El XML declara la ReteICA como porcentaje verdadero (`0.966`); el catálogo de SIIGO guarda esa
misma tarifa **por mil** (`9.66`). Comparar los dos números sin convertir da un factor de diez,
que en una retención es dinero de un tercero retenido de más o de menos.
"""

from typing import Optional

#: Esquemas de la DIAN que son retenciones, y el tipo con el que se nombran en el sistema.
#:
#: La nomenclatura coincide con la del catálogo (`integration_taxes.type`) y con la que usa el
#: llm-service, para que las tres capas hablen de lo mismo con las mismas palabras.
ESQUEMAS_DE_RETENCION = {
    "06": "retefuente",  # ReteRenta en el XML; retención en la fuente
    "07": "reteica",
    "08": "reteiva",
}

#: Retenciones cuya tarifa el catálogo de SIIGO expresa POR MIL en vez de por ciento.
#:
#: Es solo la ReteICA. Se comprobó contra el ambiente real: SIIGO retuvo 370,68 sobre una base
#: de 42.804,00, que es exactamente 8,66/1000 y no 8,66/100.
TARIFAS_POR_MIL = frozenset({"reteica"})


def _numero(valor, por_defecto: float = 0.0) -> float:
    if valor is None:
        return por_defecto
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto


def extraer_retenciones_del_xml(retenciones_del_xml) -> list[dict]:
    """Las retenciones que el proveedor declara, normalizadas.

    Cada elemento lleva `esquema`, `tipo`, `nombre`, `porcentaje`, `base` y `valor`.

    Se descarta lo que no es una retención practicada: los esquemas que no lo son, y las que
    llegan con valor cero — una retención de cero no se practicó, y arrastrarla solo produciría
    ruido al contrastar.
    """
    resultado: list[dict] = []
    for bruto in retenciones_del_xml or []:
        if not isinstance(bruto, dict):
            continue

        esquema = str(bruto.get("codigo") or "").strip()
        tipo = ESQUEMAS_DE_RETENCION.get(esquema)
        if tipo is None:
            continue

        valor = _numero(bruto.get("valor"))
        if valor == 0:
            continue

        resultado.append(
            {
                "esquema": esquema,
                "tipo": tipo,
                "nombre": (bruto.get("nombre") or "").strip() or None,
                "porcentaje": _numero(bruto.get("porcentaje")),
                "base": _numero(bruto.get("base_imponible")),
                "valor": valor,
            }
        )
    return resultado


def total_retenido(retenciones: list[dict]) -> float:
    """Lo que el proveedor declara que se le retuvo, en total."""
    return round(sum(r.get("valor") or 0 for r in retenciones or []), 2)


def tarifa_en_unidades_de_siigo(porcentaje: float, tipo: str) -> Optional[float]:
    """La tarifa del XML expresada como la guarda el catálogo de SIIGO.

    Existe para que comparar las dos puntas sea una operación explícita y no un descuido. El
    XML dice «0.966 %» donde el catálogo dice «9.66 por mil»: son la misma retención, y
    compararlas en crudo da un factor de diez.
    """
    if porcentaje is None:
        return None
    return round(porcentaje * 10, 4) if tipo in TARIFAS_POR_MIL else round(porcentaje, 4)
