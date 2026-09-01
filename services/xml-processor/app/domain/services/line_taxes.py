"""Los impuestos de una línea de la factura, todos, tal como los declara la DIAN.

El defecto que este módulo corrige
-----------------------------------
Al construir las líneas se tomaba `(item["impuestos"] or [{}])[0]`: el primer subtotal de
impuesto y nada más. Todo lo que viniera después se descartaba sin dejar rastro.

Medido sobre los 45 XML reales del cliente, contrastando `documents.total_taxes` contra la
suma de `document_details.tax_value`: **19 documentos pierden impuesto, por $7.363,44**.

La causa son ocho facturas de telecomunicaciones que declaran dos impuestos en la MISMA
línea —IVA 19 % e impuesto al consumo 4 %—. Se conservaba el IVA y se perdía el INC. Después,
la línea de ajuste que el sistema añade para cuadrar el total tapaba la diferencia, y por eso
el defecto no tenía síntoma: el documento quedaba contabilizado en verde, por el importe
correcto, con la naturaleza contable equivocada.

Por qué la lista completa importa aunque el total cuadre
---------------------------------------------------------
Un impuesto al consumo contabilizado como «ajuste» contra una cuenta genérica no es el mismo
asiento que un impuesto al consumo. El total coincide; la contabilidad, no. Y cuando llegue
una factura donde el ajuste no cuadre exactamente, no habrá forma de saber qué faltaba.
"""

from typing import Optional

#: Esquemas de la DIAN que son impuesto al consumo.
#:
#: Los tres cuentan como INC para el contador aunque la DIAN les dé código propio: «04» es el
#: impuesto al consumo general, «02» el IC y «22» el de bolsas plásticas. Se listan aquí, con
#: los demás esquemas, para que exista UNA sola definición de qué es INC en el servicio.
ESQUEMAS_DE_CONSUMO = frozenset({"02", "04", "22"})


#: Esquema de la DIAN del IVA.
ESQUEMA_IVA = "01"


def desglose_de_impuesto(impuestos, esquemas) -> tuple:
    """`(porcentaje, valor)` de los impuestos de la línea que pertenecen a esos esquemas.

    Devuelve las dos cifras POR SEPARADO porque son dos datos distintos y el contador los usa
    para cosas distintas: la tarifa para verificar que se aplicó la que correspondía, y el
    importe para cuadrar la cuenta. Mezclarlas en un solo campo fue justo lo que dejó al INC
    sin porcentaje visible.

    - `valor` suma todas las entradas del grupo.
    - `porcentaje` es `None` cuando no se puede afirmar uno solo: porque no hay entradas,
      porque la tarifa no viene, o porque la línea trae dos del mismo grupo con tarifas
      distintas. En ese último caso el importe sí es la suma, pero **no existe** un porcentaje
      único que lo explique, y devolver cualquiera de los dos sería inventarlo.
    """
    entradas = [
        i
        for i in (impuestos or [])
        if isinstance(i, dict) and str(i.get("esquema") or "").strip().upper() in esquemas
    ]
    if not entradas:
        return None, 0.0

    valor = round(sum(_numero(i.get("valor")) for i in entradas), 2)
    tarifas = {_numero(i.get("porcentaje")) for i in entradas}
    tarifas.discard(0.0)
    porcentaje = tarifas.pop() if len(tarifas) == 1 else None
    return porcentaje, valor


def impuesto_al_consumo(impuestos) -> float:
    """Cuánto INC declara esta línea, sumando todos sus esquemas de consumo.

    Una línea puede llevar IVA e INC a la vez —las facturas de telecomunicaciones lo hacen— y
    `tax_value` solo conserva el impuesto principal, que es el de mayor importe. Por eso el
    INC no se puede deducir de las columnas que ya existían: hay que leerlo de la lista
    completa de impuestos de la línea.
    """
    return desglose_de_impuesto(impuestos, ESQUEMAS_DE_CONSUMO)[1]


#: Esquemas de la DIAN que no representan un impuesto que enlazar ni sumar.
#:
#: «ZZ» es literalmente «No aplica»: aparece en las líneas exentas, con porcentaje cero, para
#: declarar que el emisor consideró el impuesto y concluyó que no procede.
ESQUEMAS_SIN_IMPUESTO = frozenset({"ZZ", ""})


def _numero(valor, por_defecto: float = 0.0) -> float:
    """El valor como número, o el de por defecto si no lo es.

    Un campo ilegible no puede tumbar la extracción del documento entero: se degrada a cero,
    que en una suma de impuestos es el elemento neutro y no altera el resto.
    """
    if valor is None:
        return por_defecto
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto


def extraer_impuestos_de_linea(impuestos_del_xml) -> list[dict]:
    """Todos los impuestos de la línea, normalizados.

    Cada elemento devuelto lleva:

    - `esquema`   — el código de la DIAN («01» IVA, «04» INC, «22» INC Bolsas, «02» IC).
    - `nombre`    — el nombre que declara el emisor.
    - `porcentaje`— la tarifa, o 0.0 cuando el impuesto es por unidad y no lleva porcentaje.
    - `base`      — la base gravable sobre la que se calculó.
    - `valor`     — el importe. Es la cifra que suma al total de la factura.
    - `por_unidad`— el monto por unidad, para los impuestos que no son porcentuales.

    Se descarta lo que no es un impuesto: el esquema «ZZ» (No aplica) y las filas con
    porcentaje y valor a cero, que no cambian ningún total y solo añadirían una referencia
    más que puede fallar al enviarse a SIIGO.
    """
    resultado: list[dict] = []
    for bruto in impuestos_del_xml or []:
        if not isinstance(bruto, dict):
            continue

        esquema = str(bruto.get("codigo") or "").strip().upper()
        if esquema in ESQUEMAS_SIN_IMPUESTO:
            continue

        porcentaje = _numero(bruto.get("porcentaje"))
        valor = _numero(bruto.get("valor"))
        por_unidad = _numero(bruto.get("valor_por_unidad"))

        # Ni tarifa ni importe: no hay nada que contabilizar ni que enviar.
        if porcentaje == 0 and valor == 0 and por_unidad == 0:
            continue

        resultado.append(
            {
                "esquema": esquema,
                "nombre": (bruto.get("nombre") or "").strip() or None,
                "porcentaje": porcentaje,
                "base": _numero(bruto.get("base_imponible")),
                "valor": valor,
                "por_unidad": por_unidad,
            }
        )
    return resultado


def impuesto_principal(impuestos: list[dict]) -> Optional[dict]:
    """El impuesto que mejor describe la línea, o None si no lleva ninguno.

    `document_details` conserva `tax_type` y `tax_value` como campos escalares porque los leen
    la interfaz y el RAG. Con varios impuestos en la línea hay que elegir cuál va ahí, y se
    elige **el de mayor importe**, no el primero que venga en el XML.

    El orden en que la DIAN los declara no significa nada; el importe sí. En las facturas de
    telecomunicaciones el IVA del 19 % es cinco veces el impuesto al consumo del 4 %: es el
    que el contador espera ver al abrir la línea.
    """
    if not impuestos:
        return None
    return max(impuestos, key=lambda i: i.get("valor") or 0)


def total_de_impuestos(impuestos: list[dict]) -> float:
    """La suma de todos los impuestos de la línea, a dos decimales.

    Es la cifra que debe cuadrar contra `documents.total_taxes`. Que dejara de cuadrar es lo
    que destapó el defecto.
    """
    return round(sum(i.get("valor") or 0 for i in impuestos or []), 2)
