"""Comprobar que lo contabilizado en SIIGO es lo que la factura dice.

El defecto que esto cierra
---------------------------
Ante `invalid_total_payments`, el envío reenvía una vez con la cifra que SIIGO dice esperar.
Reenviar ahí es correcto —es un rechazo previo a la escritura, no hay comprobante creado que
se pueda duplicar—, pero **SIIGO calcula ese total a partir de los ítems que nosotros le
mandamos**. Si una línea está mal extraída, SIIGO devuelve el total coherente con esa línea
mal extraída, y el reenvío lo acepta como si fuera la verdad.

El documento quedaba entonces en CONTABILIZADO, sin advertencia, por un importe distinto al
que la DIAN declara. Un error de extracción se convertía en una contabilización limpia: nadie
lo iba a encontrar, porque nada parecía roto.

Qué hace esta comprobación, y qué no hace
------------------------------------------
**No impide contabilizar.** Cuando llega aquí, la factura ya existe en SIIGO y nada puede
deshacerla; negarse a registrar el resultado solo añadiría un documento en estado incierto a
un comprobante que sí se creó.

Lo que hace es **dejar constancia**. La diferencia se guarda junto al documento y se muestra,
de modo que alguien pueda encontrarla. Es la distinción entre un error silencioso y uno
visible, que es toda la diferencia que hay aquí.
"""

from dataclasses import dataclass
from typing import Optional

#: Diferencia por debajo de la cual no hay descuadre que revisar.
#:
#: La DIAN redondea sus totales a peso: nueve de los 45 XML del cliente traen
#: `PayableRoundingAmount` distinto de cero. Una diferencia de céntimos es ese redondeo, y
#: marcarla haría que la alerta perdiera todo su valor por repetirse en documentos correctos.
TOLERANCIA_DE_REDONDEO = 1.0


@dataclass(frozen=True)
class VerificacionDelTotal:
    """El resultado de contrastar lo contabilizado contra lo facturado.

    `comprobado` y `coincide` son distintos a propósito. `comprobado=False` significa que no
    hubo con qué comparar —SIIGO no devolvió el total, o el documento no lo tiene—, y en ese
    caso `coincide` es None y no False: no se afirma que cuadre ni que descuadre. Dar por
    bueno lo que no se ha comprobado es justamente lo que producía el defecto.
    """

    comprobado: bool
    coincide: Optional[bool]
    diferencia: float
    total_siigo: Optional[float]
    total_dian: Optional[float]
    mensaje: Optional[str]


def _numero(valor) -> Optional[float]:
    if valor is None:
        return None
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return None


def total_de_la_respuesta(respuesta) -> Optional[float]:
    """El total que SIIGO informa al aceptar la factura, o None.

    Es el único dato de la respuesta que permite comprobar el importe: `PurchasesOut` no
    devuelve las retenciones aplicadas, así que `total` y `balance` son lo único observable.

    Se busca en los dos sitios porque el cuerpo llega ENVUELTO. El siigo-service responde
    `{"siigo_id": …, "siigo_name": …, "siigo_response": {…}}` y el total de SIIGO vive dentro
    de `siigo_response`. Mirar solo la raíz devolvía None siempre, y `documents.siigo_total`
    quedaba vacío en todos los documentos — justo el hueco que esa columna venía a cerrar.
    """
    if not isinstance(respuesta, dict):
        return None

    anidada = respuesta.get("siigo_response")
    if isinstance(anidada, dict):
        total = _numero(anidada.get("total"))
        if total is not None:
            return total

    return _numero(respuesta.get("total"))


def verificar_total_contabilizado(total_siigo, total_dian) -> VerificacionDelTotal:
    """Contrasta el total que SIIGO contabilizó con el que declara la factura de la DIAN."""
    siigo = _numero(total_siigo)
    dian = _numero(total_dian)

    if siigo is None or dian is None:
        return VerificacionDelTotal(
            comprobado=False,
            coincide=None,
            diferencia=0.0,
            total_siigo=siigo,
            total_dian=dian,
            mensaje=None,
        )

    diferencia = round(siigo - dian, 2)
    if abs(diferencia) < TOLERANCIA_DE_REDONDEO:
        return VerificacionDelTotal(
            comprobado=True,
            coincide=True,
            diferencia=diferencia,
            total_siigo=siigo,
            total_dian=dian,
            mensaje=None,
        )

    # El mensaje va dirigido al contador y nombra las dos cifras, para que pueda comparar sin
    # abrir SIIGO. Y dice explícitamente que la factura ya existe: la acción correcta es
    # verificar y corregir en SIIGO, nunca reenviar — reenviar duplicaría un asiento real.
    mensaje = (
        f"El documento se contabilizó en SIIGO por {siigo:,.2f} y la factura de la DIAN "
        f"declara {dian:,.2f}: hay una diferencia de {abs(diferencia):,.2f}. "
        "El comprobante YA existe en SIIGO, así que no debe reenviarse. Revise las líneas "
        "del documento y corrija el comprobante directamente en SIIGO."
    ).replace(",", ".")

    return VerificacionDelTotal(
        comprobado=True,
        coincide=False,
        diferencia=diferencia,
        total_siigo=siigo,
        total_dian=dian,
        mensaje=mensaje,
    )
