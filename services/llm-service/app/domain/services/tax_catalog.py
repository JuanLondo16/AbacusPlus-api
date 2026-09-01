"""RF-08 · Lectura estructurada de los catálogos de Impuestos y Retenciones.

Hasta el 2026-08-31 existía una sola tabla, `integration_taxes`, que mezclaba impuestos
reales del documento (IVA, Impoconsumo, AdValorem) con retenciones (ReteFuente, ReteICA,
ReteIVA, Autorretención). Ese día se separaron en dos tablas físicas —`integration_taxes`
para impuestos, `integration_retentions` para retenciones—, pero ambas se sincronizan desde
la misma fuente (SIIGO) con el mismo vocabulario de `type`, así que la lectura estructurada
que sigue sirve para las dos: es la única fuente del `tax_id` y del porcentaje con el que se
calcula cualquier retención, sea cual sea la tabla de la que venga la fila.

Llegaba al sugeridor como una lista plana de la que solo se descartaba el IVA, y esa lectura
tan pobre tenía dos consecuencias medibles en la data real del cliente (antes de la
separación física, cuando ambas cosas todavía convivían en `integration_taxes`):

1. **Se ofrecían como retención cosas que no lo son.** En el catálogo del tenant conviven
   `Impoconsumo 8%`, `Impoconsumo por valor` y `autorretencion`. El impoconsumo es un impuesto
   del documento, como el IVA, no algo que el comprador retenga al proveedor; y la
   autorretención, en palabras del contador del cliente, «es un cálculo que se hace sobre las
   ventas, mas no por las compras». Ninguna de las dos procede jamás en una factura de compra,
   y sin embargo se le entregaban al modelo como candidatas legítimas.
2. **Las filas gemelas rompían el determinismo.** El upsert del catálogo es por `name`, así
   que sincronizar desde SIIGO y además importar un Excel deja pares como «IVA 19%» / «IVA
   19%.» o «autorretencion» / «autorretención.». Cuando eso ocurre con una retención, el
   modelo tiene dos identificadores válidos para exactamente la misma tarifa y puede devolver
   uno u otro en cada ejecución. El prompt exige determinismo; el catálogo lo impedía.

Este módulo es la lectura estructurada que faltaba: clasifica cada fila por su naturaleza
tributaria, deja pasar solo lo que un comprador puede practicarle a su proveedor y colapsa
las filas gemelas de forma estable. No define ninguna tarifa ni añade impuestos: solo
interpreta lo que ya está en la tabla.

La nomenclatura de clases (`retefuente` · `reteica` · `reteiva`) es deliberadamente la misma
que usa el xml-processor al indexar el conocimiento validado
(`domain/services/rag_content._retention_type`). Un caso histórico etiquetado como
`retefuente` tiene que poder filtrarse con el mismo término con que aquí se clasifica el
catálogo; dos vocabularios para lo mismo significan que el filtro no encuentra nada.
"""

import unicodedata
from typing import Any, Optional

#: Clases que un comprador puede practicarle al proveedor en una factura de compra.
#:
#: Son exactamente las tres que nombra RF-08 («Retención en la fuente, RETEICA y RETEIVA»).
#: Todo lo demás que viva en el catálogo —IVA, impoconsumo, autorretención— es un impuesto del
#: documento o un cálculo sobre las ventas propias, y no una retención de esta operación.
#:
#: La ReteFuente es tributariamente practicable pero no llega a SIIGO —`POST /v1/purchases`
#: no tiene dónde recibirla—, así que sigue siendo candidata AQUÍ (la valida toda la misma
#: tabla de tarifas, base mínima y autorretenedor que las demás) y se retira después, ya
#: validada, en `SuggestRetentionsUseCase._exclude_unsendable`. Excluirla en esta puerta en
#: vez de en esa habría significado que ninguna de esas reglas se ejerciera nunca sobre ella.
PRACTICABLE_ON_PURCHASE = frozenset({"retefuente", "reteica", "reteiva"})

#: Clase de las filas que representan el IVA facturado. Es la base de la ReteIVA, así que se
#: identifica aparte en lugar de tratarse como «todo lo que no es retención».
IVA = "iva"

#: Etiquetas legibles de por qué una clase no procede. Se le muestran al contador, así que
#: dicen el motivo tributario y no el nombre de la comprobación.
_MOTIVO_NO_PRACTICABLE = {
    "iva": "el IVA es un impuesto del ítem que llega en el XML, no una retención del documento",
    "impoconsumo": (
        "el impoconsumo es un impuesto del documento, no una retención que el comprador "
        "practique al proveedor"
    ),
    "autorretencion": (
        "la autorretención se calcula sobre las ventas propias, no sobre las compras, así que "
        "no procede en una factura recibida de un proveedor"
    ),
}


#: Aviso de la fila cuyo tributo no se reconoce. No se descarta en silencio: un rótulo nuevo
#: de SIIGO no debe traducirse en una retención que deja de proponerse sin explicación.
_MOTIVO_DESCONOCIDO = (
    "no se reconoce el tributo a partir de su tipo ni de su nombre. Si es una retención que "
    "la empresa practica, revise cómo viene rotulada en el catálogo de Impuestos"
)


def _normalize(value: Any) -> str:
    """Minúsculas, sin tildes, sin espacios ni puntuación de separación.

    «ReteICA», «Rete ICA» y «rete-ica» son la misma cosa escrita por tres integraciones
    distintas; y «autorretención.» es la fila gemela de «autorretencion» que dejó una
    importación de Excel. Comparar sobre esta forma es lo que permite reconocerlas.
    """
    texto = unicodedata.normalize("NFKD", str(value or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return "".join(c for c in texto.lower() if c.isalnum())


def classify(tax: dict) -> str:
    """Clase tributaria de una fila del catálogo de Impuestos.

    Se decide primero por `type`, que es el campo que SIIGO llena con su propia taxonomía
    (`IVA`, `Retefuente`, `ReteICA`, `Impoconsumo`, `Autorretencion`), y solo si ese campo no
    dice nada reconocible se recurre al `name`. El orden importa: el nombre es texto libre que
    el contador puede editar, y el tipo no.

    Una fila que no encaja en ninguna clase conocida devuelve `""`. No se adivina: un catálogo
    puede traer tributos que este código no conoce, y atribuirles una clase equivocada sería
    peor que declararlos desconocidos.
    """
    for campo in ("type", "name"):
        clase = _classify_text(tax.get(campo))
        if clase:
            return clase
    return ""


def _classify_text(value: Any) -> str:
    texto = _normalize(value)
    if not texto:
        return ""
    # La autorretención se comprueba antes que la retención en la fuente porque su nombre la
    # contiene: «autorretencion» incluye «retencion», y clasificarla como ReteFuente sería
    # justo el error que este módulo existe para impedir.
    if "autorreten" in texto:
        return "autorretencion"
    if "reteiva" in texto or "retencioniva" in texto:
        return "reteiva"
    if "reteica" in texto or "retencionica" in texto:
        return "reteica"
    if "retefuente" in texto or "retefte" in texto or "retencionenlafuente" in texto:
        return "retefuente"
    if "impoconsumo" in texto or texto == "inc":
        return "impoconsumo"
    if "iva" in texto:
        return IVA
    return ""


def motivo_no_practicable(clase: str) -> Optional[str]:
    """Por qué una clase no puede proponerse como retención de una factura de compra."""
    return _MOTIVO_NO_PRACTICABLE.get(clase)


def is_practicable_on_purchase(clase: str) -> bool:
    return clase in PRACTICABLE_ON_PURCHASE


def retention_candidates(catalog: list[dict]) -> tuple[list[dict], list[str]]:
    """Retenciones que un comprador puede practicar.

    Desde la migración del 2026-08-31 se llama con DOS catálogos distintos, según el llamador:
    `integration_taxes` (ya no trae retenciones, solo sirve para clasificar tipos registrados
    en `_excluding_registered_types`) e `integration_retentions` (la fuente real de
    candidatas). La función es agnóstica a cuál de las dos tablas viene cada fila: clasifica
    por `type`/`name` igual en ambas, porque `integration_retentions` normaliza `type` con la
    misma nomenclatura (`retefuente` · `reteica` · `reteiva` · `autorretencion`).

    Para `type='reteica'`, `integration_retentions` trae además el municipio, el concepto y la
    base mínima en la MISMA fila — antes esa información solo existía en una tabla paralela
    del xml-processor (`retention_ica_rates`) que había que cruzar por porcentaje, y ese cruce
    casi nunca coincidía con las tarifas planas sincronizadas de SIIGO. Esos campos viajan tal
    cual si la fila los trae (`None` en cualquier otro tipo), así que el modelo y el validador
    ya no necesitan consultar ninguna tabla aparte para saber si una ReteICA es verificable:
    elegir su `id` ya implica un municipio, un concepto y una base mínima consistentes entre sí.

    Devuelve las candidatas ya clasificadas y normalizadas, más los avisos que explican qué se
    dejó fuera y por qué. Los avisos no son decoración: sin ellos, un catálogo mal sincronizado
    produce «la IA no identificó retenciones» sin que nadie pueda saber si es que no procedían
    o es que la tabla no traía ninguna retención utilizable.

    Se aplican tres criterios, en este orden:

    1. **Fila utilizable.** Sin `id` no hay nada que proponer —el `tax_id` es lo que se
       persiste— y sin porcentaje positivo la retención valdría cero. Las filas inactivas se
       excluyen: el contador las desactivó por algo.
    2. **Clase practicable.** Solo ReteFuente, ReteICA y ReteIVA. Lo demás se descarta con su
       motivo tributario.
    3. **Una fila por (clase, porcentaje, nombre).** Ante filas gemelas se conserva la de
       menor `id`, en silencio: producen el mismo cálculo, así que cuál se use no es una
       decisión del contador. Elegir siempre la misma es lo que hace la sugerencia repetible.
    """
    avisos: list[str] = []
    descartadas_por_clase: dict[str, set[str]] = {}
    candidatas: list[dict] = []

    for tax in catalog or []:
        tax_id = tax.get("id")
        if tax_id is None or tax.get("active") is False:
            continue
        try:
            percentage = float(tax.get("percentage") or 0)
        except (TypeError, ValueError):
            percentage = 0.0

        nombre = str(tax.get("name") or "")
        clase = classify(tax)

        if not is_practicable_on_purchase(clase):
            # Solo se avisa de lo que el usuario podría necesitar corregir.
            #
            # Que el catálogo traiga IVA, impoconsumo o autorretención no es un problema: los
            # trae SIEMPRE, porque son tributos que la empresa usa para otras cosas. Avisar de
            # ellos en cada sugerencia de cada documento llenaba la pantalla de advertencias
            # que decían lo mismo una y otra vez, y enterraba la única que hablaba de esta
            # factura. Un aviso que aparece siempre no informa: entrena a ignorarlos todos.
            #
            # Un tributo que NO se reconoce sí se avisa, y por lo contrario: es raro, y si
            # SIIGO rotulara la ReteICA con una palabra que este código no contempla, la fila
            # desaparecería sin dejar rastro.
            if motivo_no_practicable(clase) is None:
                descartadas_por_clase.setdefault(_MOTIVO_DESCONOCIDO, set()).add(
                    nombre or str(tax_id)
                )
            continue

        if percentage <= 0:
            avisos.append(
                f"«{nombre}» está en el catálogo de Impuestos sin porcentaje: no se puede "
                "calcular la retención, así que no se propone. Revise la fila en Impuestos."
            )
            continue

        candidatas.append(
            {
                "id": int(tax_id),
                "name": nombre,
                # `type` conserva el valor original del catálogo, que es lo que el contador ve
                # en la pantalla de Impuestos; `clase` es la lectura normalizada con la que
                # decide el sistema. Separarlos evita que una diferencia de escritura entre
                # SIIGO y el Excel cambie el comportamiento.
                "type": str(tax.get("type") or ""),
                "clase": clase,
                "percentage": percentage,
                # Solo presentes cuando la fila viene de `integration_retentions` con
                # `type='reteica'`; `None` en cualquier otro caso (incluida cualquier fila de
                # `integration_taxes`, que nunca los trae). Viajan tal cual para que el
                # candidato sea autosuficiente: municipio, concepto, tarifa y base mínima en
                # el mismo objeto, sin tener que cruzarlo con ninguna otra tabla.
                "municipality_code": tax.get("municipality_code"),
                "municipality_name": tax.get("municipality_name"),
                "retention_concept": tax.get("retention_concept"),
                "minimum_base_uvt": tax.get("minimum_base_uvt"),
            }
        )

    for motivo, nombres in sorted(descartadas_por_clase.items()):
        avisos.append(
            "No se proponen " + ", ".join(f"«{n}»" for n in sorted(nombres)) + f": {motivo}."
        )

    candidatas, avisos_duplicados = _collapse_duplicates(candidatas)
    return candidatas, avisos + avisos_duplicados


def _collapse_duplicates(candidatas: list[dict]) -> tuple[list[dict], list[str]]:
    """Deja una sola fila por (clase, porcentaje, **nombre**), la de menor `id`.

    El nombre forma parte de la clave, y esa es la diferencia entre depurar y perder datos.
    «Retefuente 4%» y «Retefuente Arriendo 4%» comparten tarifa pero **no son la misma
    retención**: responden a conceptos tributarios distintos y en SIIGO cuelgan de cuentas
    distintas, así que quedarse con una de las dos le quitaría al contador la opción correcta
    —y contabilizaría contra la cuenta equivocada— sin que nada lo advirtiera.

    Lo que sí es una fila gemela es la que repite el mismo nombre salvo por la puntuación o
    las tildes: «ReteIVA 15%» y «ReteIVA 15%.», que es lo que deja combinar la sincronización
    de SIIGO con una importación de Excel. Esas dos sí son la misma retención escrita dos
    veces, y tener dos identificadores para ella hace que la sugerencia cambie entre
    ejecuciones.
    """
    por_clave: dict[tuple[str, float, str], list[dict]] = {}
    for c in candidatas:
        clave = (c["clase"], round(c["percentage"], 6), _normalize(c["name"]))
        por_clave.setdefault(clave, []).append(c)

    resultado: list[dict] = []
    for filas in por_clave.values():
        # Se elige la de menor `id` y **no se avisa**. Dos filas activas con el mismo nombre,
        # la misma clase y la misma tarifa son la misma retención escrita dos veces: cualquiera
        # de las dos produce el mismo cálculo y el mismo asiento, así que cuál se use no es una
        # decisión que el contador necesite tomar en cada documento. Lo único que hay que
        # garantizar es elegir SIEMPRE la misma, para que la sugerencia no cambie entre
        # ejecuciones; el `id` menor es un criterio estable y es además el que ya referencian
        # las retenciones registradas antes.
        filas.sort(key=lambda f: f["id"])
        resultado.append(filas[0])
    resultado.sort(key=lambda f: f["id"])
    return resultado, []


#: Tope de renglones del desglose que viajan al prompt.
#:
#: Los agregados (`iva`, `por_clase`) se calculan sobre **todas** las líneas: son los que
#: deciden la base de la ReteIVA y no pueden depender de un recorte. Lo que se acota es el
#: detalle línea a línea, que solo sirve para que el modelo acote la base a unos renglones
#: concretos. Una factura de supermercado con cientos de ítems multiplicaría el tamaño del
#: prompt —y su coste, y la latencia— sin mejorar la decisión. El mismo tope que ya usa la
#: lista de renglones del documento.
_MAX_RENGLONES_PROMPT = 20


def document_tax_breakdown(document: dict, catalog: list[dict]) -> dict[str, Any]:
    """Impuestos del propio documento, resueltos contra el catálogo de Impuestos.

    Cada línea del XML llega ya enlazada al catálogo por `tax_id` (lo hace el xml-processor al
    procesar la factura), pero esa información no salía del backend: al modelo solo le llegaba
    `total_taxes`, que es **la suma de todos los impuestos del documento**, no el IVA. En una
    factura con impoconsumo o con INC de bolsas, usar ese total como base de la ReteIVA retiene
    sobre un importe que no es el IVA — de más, y sobre dinero real de un tercero.

    Aquí se reconstruye el desglose: cuánto IVA hay, cuánto de cada otro impuesto, y en qué
    renglones. `iva` es la cifra que debe usarse como base de la ReteIVA; `total_declarado` se
    conserva para que la diferencia entre ambos sea visible en vez de silenciosa.
    """
    por_id = {t["id"]: t for t in catalog or [] if t.get("id") is not None}
    por_clase: dict[str, float] = {}
    renglones: list[dict] = []

    for detalle in document.get("details") or []:
        valor = _float(detalle.get("tax_value"))
        tax_id = detalle.get("tax_id")
        fila = por_id.get(tax_id) if tax_id is not None else None
        clase = classify(fila) if fila else ""
        if valor:
            por_clase[clase or "sin_clasificar"] = round(
                por_clase.get(clase or "sin_clasificar", 0.0) + valor, 2
            )
        if tax_id is None and not valor:
            continue
        renglones.append(
            {
                "detail_id": detalle.get("id"),
                "tax_id": tax_id,
                "impuesto": str((fila or {}).get("name") or ""),
                "clase": clase,
                # El XML guarda el porcentaje como texto en `tax_type`; se prefiere el del
                # catálogo cuando la línea está enlazada, porque es el que el sistema usaría
                # para calcular.
                "porcentaje": _float((fila or {}).get("percentage"))
                if fila
                else _float(detalle.get("tax_type")),
                "valor": valor,
                "base": _float(detalle.get("subtotal")),
            }
        )

    total_declarado = _float(document.get("total_taxes"))
    iva = por_clase.get(IVA)
    # Se declara cuántos había cuando se recorta, para que el modelo no lea el detalle como
    # si fuera la factura entera y acote la base sobre una parte creyéndola el todo.
    recortados = max(0, len(renglones) - _MAX_RENGLONES_PROMPT)
    return {
        # Base de la ReteIVA. Si ninguna línea está enlazada al catálogo no se puede afirmar
        # cuánto del total es IVA, así que se deja en None y quien calcula decide: es
        # preferible declarar que no se sabe a devolver una cifra que puede no ser el IVA.
        "iva": iva,
        "por_clase": por_clase,
        "total_declarado": total_declarado,
        "renglones": renglones[:_MAX_RENGLONES_PROMPT],
        **({"renglones_omitidos": recortados} if recortados else {}),
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
