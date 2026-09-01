"""La tabla de tarifas de ReteICA tiene que estar toda en la misma unidad.

Copia deliberada de `xml-processor/app/domain/services/ica_rate_units.py`: el proyecto no
comparte código entre microservicios ("Dominio independiente"), y la importación de
municipios de ReteICA se repunta a este servicio (dueño de `integration_retentions`), así
que la misma comprobación de seguridad tiene que existir aquí también.

El ICA se publica tradicionalmente **por mil** (Bogotá servicios: 9,66 por mil = 0,966 %).
Un Excel puede traer las dos formas sin que nadie lo note, y aplicar una convención a filas
que están en la otra retiene diez veces de más o de menos sobre dinero de un tercero. Se
rechaza el archivo entero en vez de adivinar cuál fila está mal.
"""

from typing import Optional

#: Las tarifas de ICA en Colombia van de ~2 a ~14 por mil (0,2 % a 1,4 %); las dos escalas no
#: se solapan, así que este umbral basta para clasificar cada fila sin conocer el catastro
#: tributario de cada municipio.
UMBRAL_POR_MIL = 1.5


class UnidadesMezcladasError(ValueError):
    """El archivo trae tarifas de ReteICA en dos unidades distintas."""


def _numero(valor) -> Optional[float]:
    if valor is None:
        return None
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _describir(fila: dict, tarifa: float) -> str:
    municipio = fila.get("municipality_name") or fila.get("municipality_code") or "?"
    concepto = fila.get("retention_concept") or "todos"
    return f"{municipio} · {concepto} → {tarifa:g}"


def verificar_unidad_coherente(filas) -> None:
    """Lanza `UnidadesMezcladasError` si el archivo mezcla por-mil y porcentaje."""
    por_mil: list[str] = []
    porcentaje: list[str] = []

    for fila in filas or []:
        if not isinstance(fila, dict):
            continue
        tarifa = _numero(fila.get("percentage"))
        if tarifa is None or tarifa <= 0:
            continue
        destino = por_mil if tarifa >= UMBRAL_POR_MIL else porcentaje
        destino.append(_describir(fila, tarifa))

    if not por_mil or not porcentaje:
        return

    raise UnidadesMezcladasError(
        "Las tarifas de ReteICA del archivo están en dos unidades distintas y no se puede "
        "importar así.\n\n"
        "Parecen estar POR MIL:\n  · "
        + "\n  · ".join(por_mil)
        + "\n\nParecen estar en PORCENTAJE:\n  · "
        + "\n  · ".join(porcentaje)
        + "\n\nSon la misma clase de tarifa escrita de dos formas —«9,66 por mil» es «0,966 %»—, "
        "y aplicar una convención a las filas de la otra retiene diez veces de más o de menos "
        "sobre dinero de un tercero.\n\n"
        "Unifique la unidad en el archivo y vuelva a importarlo. El catálogo de retenciones "
        "usa POR MIL para ReteICA, igual que SIIGO."
    )
