"""Traducción del impuesto que trae el XML al identificador del catálogo de SIIGO.

El XML de la DIAN describe el impuesto de una línea por su **porcentaje** —«19.00», «8.00»—;
SIIGO lo espera por el **id** de su catálogo. Este módulo es el único sitio donde se hace esa
traducción.

Por qué vive solo y no dentro de un caso de uso
-----------------------------------------------
La misma pregunta se respondía en dos sitios con reglas distintas, y respondían distinto:

- Al **guardar** el documento se comparaba primero por nombre y luego por porcentaje, sin
  preferir ningún tipo ni desempatar entre gemelos. Escribía `document_details.tax_id`.
- Al **enviar** a SIIGO se indexaba por porcentaje, prefiriendo el tipo IVA y quedándose con
  el id menor.

En la factura F78P21635 eso produjo dos líneas con `tax_id` nulo en la base y un envío con
`tax_ids: [10609]`. La interfaz mostraba la línea sin impuesto mientras a SIIGO iba uno, y no
había forma de saber cuál mandaba. Con una función compartida, las dos capas no pueden volver
a divergir.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: Margen al comparar porcentajes. El XML emite «19.00» y el catálogo puede guardar 19 o
#: 19.0000; son la misma tarifa. Es holgado para el formato y estrecho para no confundir
#: tarifas realmente distintas, que en el régimen colombiano nunca están a menos de un punto.
TOLERANCIA = 0.01

#: Tipo que se prefiere cuando varios impuestos comparten porcentaje.
#:
#: El catálogo del cliente tiene cinco impuestos al 19 %, de tipos distintos. En una línea de
#: una factura de compra el impuesto que suma sobre la base es el IVA, así que ante un empate
#: es el que corresponde. Solo cuando ningún IVA tiene ese porcentaje se recurre a otro tipo,
#: y es lo que resuelve el 8 %, que en este catálogo es Impoconsumo.
TIPO_PREFERIDO = "iva"


def _porcentaje(valor) -> Optional[float]:
    """El porcentaje como número, o None si no lo es.

    Una fila del catálogo con el porcentaje ilegible se ignora en lugar de tumbar la
    resolución del documento entero: el resto del catálogo sigue siendo utilizable.
    """
    if valor is None:
        return None
    try:
        return round(float(str(valor).strip()), 2)
    except (TypeError, ValueError):
        return None


def indice_por_porcentaje(catalogo) -> dict:
    """Porcentaje → id del impuesto que le corresponde.

    Precalcula la misma decisión que `resolver_impuesto` para no recorrer el catálogo una vez
    por línea. Es la forma que conviene al construir el envío, donde se resuelven todas las
    líneas del documento de una vez.

    El 0 % se excluye a propósito: una línea exenta no lleva impuesto.
    """
    if not catalogo:
        return {}

    mejor: dict = {}
    for fila in catalogo:
        pct = _porcentaje(fila.get("percentage"))
        if pct is None or pct == 0:
            continue
        try:
            id_impuesto = int(fila.get("id"))
        except (TypeError, ValueError):
            continue

        es_preferido = str(fila.get("type") or "").strip().lower() == TIPO_PREFERIDO
        actual = mejor.get(pct)
        if actual is None:
            mejor[pct] = (id_impuesto, es_preferido)
            continue

        id_actual, actual_preferido = actual
        # Manda el tipo preferido; entre iguales, el id menor. El catálogo base de SIIGO
        # tiene los ids bajos y las importaciones de Excel añaden gemelos con ids muy
        # superiores («IVA 19%» / «IVA 19%.»); quedarse siempre con el menor hace que la
        # misma línea se resuelva igual en cada ejecución.
        if (es_preferido and not actual_preferido) or (
            es_preferido == actual_preferido and id_impuesto < id_actual
        ):
            mejor[pct] = (id_impuesto, es_preferido)

    return {pct: datos[0] for pct, datos in mejor.items()}


def resolver_impuesto(porcentaje, catalogo, *, nombre: Optional[str] = None) -> Optional[int]:
    """Id del impuesto del catálogo que corresponde a ese porcentaje, o None.

    Devolver None es una respuesta legítima y frecuente: una línea exenta, un catálogo que no
    llegó, o un porcentaje que la empresa no tiene configurado. **No se aproxima al más
    cercano**: enlazar al impuesto equivocado es peor que no enlazar, porque queda registrado
    como si fuera una decisión.

    `nombre` es un último recurso para los catálogos importados desde Excel cuyo nombre es
    literalmente el número y cuyo porcentaje quedó vacío. Se consulta **después** del
    porcentaje, no antes: el porcentaje es el dato fiable y el nombre es texto libre.
    """
    pct = _porcentaje(porcentaje)
    if pct is None or pct == 0 or not catalogo:
        return None

    indice = indice_por_porcentaje(catalogo)
    for clave, id_impuesto in indice.items():
        if abs(clave - pct) < TOLERANCIA:
            return id_impuesto

    if nombre:
        buscado = str(nombre).strip().lower()
        for fila in catalogo:
            if str(fila.get("name") or "").strip().lower() == buscado:
                try:
                    return int(fila.get("id"))
                except (TypeError, ValueError):
                    break

    logger.warning(
        "Ningún impuesto del catálogo tiene el %s%% que trae la línea. Queda sin enlazar: "
        "la interfaz no mostrará su impuesto y el total enviado a SIIGO puede no cuadrar.",
        pct,
    )
    return None
