"""Qué impuestos pueden viajar juntos dentro de una línea de `POST /v1/purchases`.

SIIGO publica estas reglas como causas del error `invalid_array` sobre `taxes`:

    - Si envías más de la cantidad de impuestos permitidos, puedes enviar hasta 3 impuestos.
    - Si envías Iva y Ad Valorem en el mismo producto de una factura.
    - Si envías un mismo tipo de impuesto más de una vez.
    - Si envías un reteIVA o reteICA en los items de factura.

Se aplican aquí, antes de enviar, por dos motivos. El primero es que **un rechazo por este
motivo tumba el documento entero**, no la línea que lo causó. El segundo es que cada rechazo
suma a la proporción de errores de la cuenta, y SIIGO bloquea el usuario de la API cuando esa
proporción supera el 80 % durante siete días: gastar peticiones en cuerpos que sabemos
inválidos tiene un coste acumulado.

La regla que faltaba era la del **tipo**. Se deduplicaba por identificador, y el catálogo del
cliente tiene cinco impuestos distintos al 19 %: dos ids del tipo IVA en la misma línea
pasaban la comprobación local y eran rechazados por SIIGO.
"""

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

#: «puedes enviar hasta 3 impuestos» por ítem.
MAX_IMPUESTOS_POR_ITEM = 3

#: Tipos que NO pueden ir en una línea. Comprobado en los dos sentidos:
#:
#: - `reteiva` y `reteica` los prohíbe el blueprint por escrito.
#: - `retefuente` y `autorretencion` los rechazó el ambiente real con
#:   `items[0].taxes → invalid_array: "The array taxes has invalid values"`.
#:
#: El motivo de fondo es que una retención **resta** del valor a pagar y un impuesto de línea
#: **suma**. Poner una donde va el otro no produce un importe distinto: produce el signo
#: contrario, que fue exactamente la confusión que descuadró cuatro documentos.
TIPOS_PROHIBIDOS_EN_LINEA = frozenset(
    {"reteiva", "reteica", "retefuente", "autorretencion", "autorretención"}
)

#: Pares de tipos que SIIGO no admite juntos en el mismo ítem, con el que se conserva.
#:
#: Se conserva el IVA porque es el impuesto que la DIAN declara en la inmensa mayoría de los
#: documentos —34 de los 45 del cliente— mientras que no hay ni un solo AdValorem en el
#: catálogo. Ante la duda, se conserva lo que sí existe.
INCOMPATIBLES = ((("iva", "advalorem"), "iva"),)


def _normalizar(tipo) -> str:
    return str(tipo or "").strip().lower()


def componer_impuestos_de_linea(
    candidatos: Iterable[tuple[Optional[int], str]],
) -> tuple[list[int], list[str]]:
    """Los impuestos que sí pueden viajar en la línea, y por qué se descartó el resto.

    Recibe pares `(id, tipo)` en el orden en que los declara el documento y devuelve
    `(ids_aceptados, avisos)`. Los avisos no son decorativos: nombran qué se dejó fuera, que
    es lo que permite al contador entender por qué el total enviado no coincide con lo que él
    ve en la factura.

    El orden de llegada se respeta. El primero de la línea es el que la DIAN declaró primero,
    y ante un descarte por tope conviene conservar los que el emisor consideró principales.
    """
    aceptados: list[int] = []
    tipos_aceptados: set = set()
    avisos: list[str] = []

    normalizados = []
    for id_impuesto, tipo in candidatos or []:
        if id_impuesto is None:
            continue
        try:
            normalizados.append((int(id_impuesto), _normalizar(tipo)))
        except (TypeError, ValueError):
            continue

    # Los incompatibles se resuelven antes del recorrido, para que el descarte no dependa del
    # orden en que lleguen. Con IVA y AdValorem en la misma línea se conserva el IVA venga
    # primero o segundo.
    presentes = {tipo for _, tipo in normalizados}
    a_excluir: set = set()
    for pareja, se_conserva in INCOMPATIBLES:
        if presentes.issuperset(pareja):
            for tipo in pareja:
                if tipo != se_conserva:
                    a_excluir.add(tipo)
                    avisos.append(
                        f"La línea traía '{tipo}' junto a '{se_conserva}' y SIIGO no admite "
                        f"esa combinación en el mismo ítem; se envía solo '{se_conserva}'."
                    )

    for id_impuesto, tipo in normalizados:
        if tipo in TIPOS_PROHIBIDOS_EN_LINEA:
            avisos.append(
                f"El impuesto {id_impuesto} es de tipo '{tipo}' y SIIGO no lo admite dentro "
                "de un ítem. Una retención se resta del valor a pagar; ponerla aquí la haría "
                "sumar."
            )
            continue
        if tipo in a_excluir:
            continue
        if id_impuesto in aceptados:
            continue
        if tipo and tipo in tipos_aceptados:
            avisos.append(
                f"La línea ya lleva un impuesto de tipo '{tipo}', así que el {id_impuesto} no "
                "se envía: SIIGO rechaza el mismo tipo repetido y con él el documento entero."
            )
            continue
        if len(aceptados) >= MAX_IMPUESTOS_POR_ITEM:
            avisos.append(
                f"La línea ya lleva {MAX_IMPUESTOS_POR_ITEM} impuestos, que es el máximo que "
                f"admite SIIGO; el {id_impuesto} no se envía."
            )
            continue

        aceptados.append(id_impuesto)
        if tipo:
            tipos_aceptados.add(tipo)

    for aviso in avisos:
        logger.warning("RF-05: %s", aviso)

    return aceptados, avisos
