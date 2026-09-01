"""La tabla de tarifas de ReteICA tiene que estar toda en la misma unidad.

El ICA se publica tradicionalmente **por mil**: la tarifa de servicios de Bogotá es «9,66 por
mil», que es 0,966 %. Las dos formas de escribirla son correctas y ambas circulan en los
documentos que maneja un contador, así que un Excel puede traer las dos sin que nadie lo note.

Lo que ocurrió de verdad en la tabla del cliente:

    Bogotá · servicios  → 9.660000   (por mil)
    Bogotá · compras    → 1.104000   (porcentaje)

Cada cifra es correcta por separado. Juntas son una bomba: quien lea la tabla aplicará una
sola convención a las dos filas, y sobre la que esté en la otra unidad retendrá **diez veces
de más o de menos** sobre dinero de un tercero.

Dónde se detecta, y por qué aquí
---------------------------------
El sistema ya lo detectaba al sugerir —RF-08 se negaba a proponer la ReteICA y lo explicaba—,
pero eso es tarde y depende de que alguien pida una sugerencia. Un dato incoherente que vive
en la base es un dato que alguien va a usar por otra vía. El sitio donde hay que pararlo es la
**importación**, que es cuando entra.

Por qué se rechaza en vez de convertir
---------------------------------------
Convertir exigiría saber cuál de las dos filas está bien, y eso no se deduce del número: 1,104
es plausible en por mil y 11,04 lo es en porcentaje. Elegir por nuestra cuenta sería la clase
de suposición que no cabe cuando el resultado se descuenta del pago a un proveedor.

Se rechaza el archivo **entero** y se nombran las filas. Importar solo la mitad coherente
dejaría la tabla igual de mezclada, y con menos rastro de por qué.
"""

from typing import Optional

#: Frontera entre las dos convenciones.
#:
#: Las tarifas de ICA en Colombia van aproximadamente de 2 a 14 por mil, es decir de 0,2 % a
#: 1,4 %. Las dos escalas **no se solapan**: por debajo de este valor la cifra solo puede ser
#: un porcentaje, y por encima solo puede ser por mil. Ese hueco es lo que permite clasificar
#: cada fila sin conocer el catastro tributario de cada municipio.
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
    """Comprueba que todas las tarifas estén en la misma unidad. Lanza si no.

    No devuelve nada: o el archivo es coherente y la importación sigue, o se detiene con un
    mensaje que nombra las filas de cada grupo para que el contador pueda ir al Excel y
    unificarlas.

    Las tarifas en cero o ilegibles se ignoran: no pertenecen a ninguna unidad y no pueden
    decidir la del archivo.
    """
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
        "Unifique la unidad en el archivo y vuelva a importarlo. El catálogo de impuestos que "
        "sincroniza SIIGO usa POR MIL, así que esa es la que hace que las dos tablas coincidan "
        "sin conversiones."
    )
