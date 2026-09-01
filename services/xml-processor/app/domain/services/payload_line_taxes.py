"""Los impuestos que viajan en una línea de `POST /v1/purchases`, y cuánto suman.

Une tres piezas que ya existen por separado:

- `line_taxes` — todos los impuestos que la DIAN declaró en la línea.
- `tax_resolution` — a qué id del catálogo corresponde cada porcentaje.
- `siigo_item_taxes` — cuáles de esos ids pueden viajar juntos según las reglas de SIIGO.

Devuelve también **el importe de impuestos de la línea**, que es un dato aparte y necesario:
SIIGO valida que `payments[].value` coincida con el total que él calcula a partir de los
ítems. Anticipar ese total contando un solo impuesto por línea deja la cifra corta y produce
`invalid_total_payments`.

El importe es «lo que SIIGO va a calcular», no «lo que declara la factura»
------------------------------------------------------------------------
Esta distinción descuadró el documento BEC520526814 en 499 pesos, y conviene dejarla escrita
porque la intuición lleva a lo contrario.

`impuesto_linea` tiene un único consumidor: `total_calculado`, con el que
`account_document` decide el tamaño de la línea de ajuste
(`faltante = total_dian - total_calculado`). Para que esa línea deje el total de SIIGO igual
al de la DIAN, `total_calculado` debe anticipar **lo que SIIGO calculará con los ids que
realmente le enviamos**. Un impuesto que no viaja no lo va a calcular nadie.

Antes se contaba también el impuesto descartado, con el razonamiento de que «existe en la
factura y omitirlo sería inventar que no está». El importe sí está —el proveedor lo cobró—,
pero quien lo aporta es la línea de ajuste, no una referencia que no se envió. Contarlo dos
veces, en el importe y en el ajuste, era imposible; contarlo en el importe y en ninguna otra
parte hacía que el ajuste saliera corto por exactamente el impuesto perdido.
"""

import logging
from typing import Optional

from app.domain.services.siigo_item_taxes import componer_impuestos_de_linea
from app.domain.services.tax_resolution import TOLERANCIA

logger = logging.getLogger(__name__)

#: Tipo del catálogo (`integration_taxes.type`, en minúsculas) que corresponde a cada esquema
#: de impuesto de la DIAN.
#:
#: Existe porque el enlace con el catálogo se hacía **solo por porcentaje**, y el porcentaje no
#: identifica un impuesto. En el catálogo del cliente no hay ningún Impoconsumo del 4 %, pero
#: sí un «Retefuente 4 %»: el INC del 4 % que declaran las facturas de telecomunicaciones se
#: enlazaba con una RETENCIÓN. Como una retención no puede viajar dentro de un ítem, el
#: impuesto se descartaba después y sus 499 pesos desaparecían del documento.
#:
#: Solo se listan los esquemas de impuestos de línea. Los de retención (06, 07, 08) no
#: aparecen a propósito: no viajan en el ítem y los resuelve `xml_withholdings`.
TIPO_POR_ESQUEMA = {
    "01": "iva",
    "02": "impoconsumo",  # IC — impuesto al consumo
    "04": "impoconsumo",  # INC
    "22": "impoconsumo",  # INC Bolsas
}


def _tipo_compatible(esquema, tipo_del_catalogo) -> bool:
    """¿El impuesto del catálogo es del tipo que ese esquema de la DIAN exige?

    Permisivo ante lo desconocido, y a propósito: si el esquema no está en el mapa o el
    catálogo no declara el tipo, se acepta el enlace y se conserva el comportamiento anterior.
    Solo se rechaza cuando se sabe qué tipo debía ser y el candidato es otro; ahí el enlace es
    demostrablemente falso.
    """
    esperado = TIPO_POR_ESQUEMA.get(str(esquema or "").strip().upper())
    if not esperado:
        return True
    tipo = str(tipo_del_catalogo or "").strip().lower()
    if not tipo:
        return True
    return tipo == esperado


def _buscar_en_indice(porcentaje: float, indice: dict) -> Optional[int]:
    """Id del catálogo para ese porcentaje, con la misma tolerancia de la resolución."""
    for clave, id_impuesto in (indice or {}).items():
        if abs(clave - porcentaje) < TOLERANCIA:
            return id_impuesto
    return None


def impuestos_de_la_linea(
    detalle,
    indice_catalogo: dict,
    tipos_por_id: dict,
    base: float = 0.0,
) -> tuple[list[int], float, list[str]]:
    """`(ids que viajan, importe de impuestos, avisos)` de una línea.

    `detalle` es la línea de `document_details`. Tres orígenes, en este orden:

    1. **`detalle.tax_id`** — el contador lo fijó a mano. Manda sobre todo lo demás.
    2. **`detalle.taxes`** — la lista completa que la DIAN declaró. Es el camino normal desde
       que se conservan todos los impuestos de la línea.
    3. **`detalle.tax_type`** — el porcentaje suelto. Es el camino de los documentos guardados
       antes de esa corrección, y se conserva para que el histórico se pueda seguir
       contabilizando exactamente igual que antes.
    """
    avisos: list[str] = []

    # 1. Lo que el contador eligió manda —pero solo sobre SU impuesto, no sobre los demás.
    #
    # `document_details.tax_id` es UNA columna: fija el impuesto principal de la línea. Al
    # tratarla como «la línea viaja con este impuesto y con ninguno más», un renglón con IVA
    # 19 % e INC 4 % —el de las facturas de telecomunicaciones— enviaba solo el IVA y perdía
    # el INC, aunque el catálogo lo tuviera. Ese campo no puede expresar dos impuestos, así
    # que interpretarlo como exclusivo convertía una limitación de la columna en una pérdida
    # de datos de la factura.
    #
    # Lo que fija es la PREFERENCIA: el id elegido va primero y, ante un descarte por las
    # reglas de SIIGO, es el que se conserva. El resto de impuestos que la DIAN declaró en la
    # línea acompañan detrás y los filtra `componer_impuestos_de_linea` como a cualquier otro.
    tax_id_manual = getattr(detalle, "tax_id", None)
    lista = getattr(detalle, "taxes", None)

    if tax_id_manual and not lista:
        # Documento antiguo: no hay desglose que acompañar. Comportamiento anterior intacto.
        tax_id_manual = int(tax_id_manual)
        importe = importe_declarado(detalle)
        if importe == 0.0:
            porcentaje = _porcentaje_de(getattr(detalle, "tax_type", None))
            importe = round(base * porcentaje / 100.0, 2)
        return [tax_id_manual], importe, avisos

    lista = getattr(detalle, "taxes", None)

    # 3. Documento antiguo: no hay lista, solo el porcentaje principal.
    if not lista:
        porcentaje = _porcentaje_de(getattr(detalle, "tax_type", None))
        if porcentaje == 0:
            return [], 0.0, avisos
        id_impuesto = _buscar_en_indice(porcentaje, indice_catalogo)
        importe = round(base * porcentaje / 100.0, 2)
        if id_impuesto is None:
            avisos.append(
                f"Ningún impuesto del catálogo tiene el {porcentaje}% de esta línea; viaja "
                "sin impuesto y su importe se traslada a la línea de ajuste."
            )
            # Mismo criterio que en el camino normal: si no viaja, SIIGO no lo calcula, así
            # que no puede contar en el total que se le anticipa.
            return [], 0.0, avisos
        return [int(id_impuesto)], importe, avisos

    # 2. Camino normal: todos los impuestos que declaró la DIAN.
    candidatos: list[tuple[Optional[int], str]] = []
    # Importe de cada candidato, para poder sumar DESPUÉS solo los que acaben viajando.
    importe_por_id: dict[int, float] = {}
    if tax_id_manual:
        # Primero el elegido: el orden decide qué se conserva si hay que descartar.
        elegido = int(tax_id_manual)
        candidatos.append((elegido, tipos_por_id.get(elegido, "")))
        importe_por_id[elegido] = _importe_del_impuesto(detalle, elegido) or 0.0
    for impuesto in lista:
        if not isinstance(impuesto, dict):
            continue
        valor = float(impuesto.get("valor") or 0)
        nombre = impuesto.get("nombre") or impuesto.get("esquema")
        esquema = impuesto.get("esquema")

        id_impuesto = impuesto.get("tax_id")
        if not id_impuesto:
            # Se reintenta contra el índice: el enlace pudo fallar al procesar el XML porque
            # el catálogo no había llegado, y para entonces ya está disponible.
            id_impuesto = _buscar_en_indice(float(impuesto.get("porcentaje") or 0), indice_catalogo)
        if not id_impuesto:
            avisos.append(
                f"El impuesto {nombre} ({impuesto.get('porcentaje')}%) de esta línea no está "
                "en el catálogo de SIIGO: no viaja como referencia y su importe se traslada a "
                "la línea de ajuste para que el total siga cuadrando."
            )
            continue

        id_impuesto = int(id_impuesto)
        if tax_id_manual and id_impuesto == int(tax_id_manual):
            continue  # ya entró como candidato preferente, con su importe
        tipo = tipos_por_id.get(id_impuesto, "")
        if not _tipo_compatible(esquema, tipo):
            # El enlace es falso: el porcentaje coincidía pero el impuesto es de otra
            # naturaleza. Enviarlo sería peor que no enviarlo —una retención dentro de un ítem
            # SUMA donde debía restar—, así que se descarta y su importe pasa al ajuste.
            avisos.append(
                f"El impuesto {nombre} (esquema {esquema}) de esta línea enlazó con el "
                f"impuesto {id_impuesto} del catálogo, que es de tipo '{tipo}'. No coinciden, "
                "así que no viaja: su importe se traslada a la línea de ajuste. Cree en SIIGO "
                f"un impuesto de tipo '{TIPO_POR_ESQUEMA.get(str(esquema or '').strip().upper())}' "
                f"con esa tarifa para que se contabilice en su propia cuenta."
            )
            logger.warning(
                "RF-05: esquema %s enlazado con el impuesto %s de tipo %r; se descarta.",
                esquema,
                id_impuesto,
                tipo,
            )
            continue

        candidatos.append((id_impuesto, tipo))
        importe_por_id[id_impuesto] = importe_por_id.get(id_impuesto, 0.0) + valor

    ids, avisos_composicion = componer_impuestos_de_linea(candidatos)
    avisos.extend(avisos_composicion)
    # Solo cuenta lo que efectivamente viaja: `componer_impuestos_de_linea` aún descarta por
    # las reglas de SIIGO (tipo repetido, tope de tres, incompatibles), y lo descartado ahí
    # tampoco lo va a calcular SIIGO.
    importe = sum(importe_por_id.get(id_impuesto, 0.0) for id_impuesto in ids)
    return ids, round(importe, 2), avisos


def _impuestos_de(detalle) -> list:
    """La lista de impuestos de la línea, ya filtrada a diccionarios."""
    return [i for i in (getattr(detalle, "taxes", None) or []) if isinstance(i, dict)]


def _importe_del_impuesto(detalle, tax_id: int) -> Optional[float]:
    """Importe que la línea declara para ESE impuesto, o None si no se puede afirmar.

    `None` no es cero: significa «este dato no está», y quien llama conserva entonces el
    comportamiento anterior en vez de dar por hecho que la línea no tiene impuestos.
    """
    lista = _impuestos_de(detalle)
    if not lista:
        return None
    coincidencias = [i for i in lista if i.get("tax_id") is not None and int(i["tax_id"]) == tax_id]
    if not coincidencias:
        return None
    return round(sum(float(i.get("valor") or 0) for i in coincidencias), 2)


def importe_declarado(detalle) -> float:
    """La suma de los impuestos que la línea declara, o 0.0 si no hay lista."""
    lista = getattr(detalle, "taxes", None)
    if not lista:
        try:
            return float(getattr(detalle, "tax_value", 0) or 0)
        except (TypeError, ValueError):
            return 0.0
    total = 0.0
    for impuesto in lista:
        if isinstance(impuesto, dict):
            total += float(impuesto.get("valor") or 0)
    return round(total, 2)


def _porcentaje_de(valor) -> float:
    try:
        return round(float(str(valor if valor is not None else "0").strip() or 0), 2)
    except (TypeError, ValueError):
        return 0.0
