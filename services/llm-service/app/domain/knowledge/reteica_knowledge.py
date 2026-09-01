"""RF-08 · Conocimiento CONCEPTUAL de ReteICA (contexto educativo, nunca fuente de tarifas).

Por qué existe este módulo
--------------------------
El prompt de RF-08 le decía al modelo *qué hacer* con la tabla de ReteICA —busca la fila del
municipio y el concepto, respeta la base mínima, no estimes— pero no le decía *qué es* el
tributo que está manipulando. Esa ausencia se notaba en los casos límite: al no saber que el
ICA es territorial y que su tarifa la fija cada municipio por actividad, el modelo trataba la
tabla como un catálogo cualquiera y, cuando la fila no aparecía, tendía a rellenar el hueco
con una tarifa «razonable» de conocimiento general en vez de declarar que faltaba el dato.
Saber por qué una tabla es la única fuente posible es lo que hace que se respete cuando está
incompleta.

De dónde sale
-------------
Del artículo oficial de Siigo «¿Qué es el ReteICA y cuándo se aplica?»
(https://www.siigo.com/blog/obligaciones-fiscales/que-es-reteica-y-cuando-se-aplica/),
incorporado como corpus curado y no como texto crudo: cada pasaje se rotula con su tema y sus
palabras clave para poder recuperarlo, y las cifras concretas del artículo viajan marcadas
como EJEMPLO ILUSTRATIVO, jamás como tarifa aplicable.

Regla que gobierna todo este módulo
-----------------------------------
**No es una fuente de tarifas ni de bases mínimas.** Es el escalón más bajo de la jerarquía de
RF-08, por debajo incluso de los precedentes contabilizados. Una tarifa que aparezca aquí
—0,772 %, «entre 0,1 % y 1 % en Medellín», «4 UVT en Bogotá»— describe *el ejemplo del
artículo*, no la configuración de esta empresa. La única fuente vinculante de una tarifa o una
base mínima sigue siendo `retention_ica_rates` (tabla cargada por el contador) y el catálogo de
Impuestos. Por eso los pasajes que traen cifras las traen dentro de un campo
`ejemplo_ilustrativo` separado del cuerpo conceptual: es la forma más barata de que el modelo
lea el número y su advertencia juntos.

Por qué está en el repositorio y no en el índice del RAG
--------------------------------------------------------
El índice vectorial de este sistema tiene una invariante estricta: solo contiene causaciones
**contabilizadas en SIIGO** (`is_validated=true`, con `siigo_id`), y la búsqueda de
precedentes se hace con `only_validated=true`. Meter doctrina ahí obligaría a romper esa
invariante o a inventar un `siigo_id` falso para un artículo de blog. La recuperación
conceptual se resuelve entonces con un retriever propio sobre este corpus —mismo contrato,
otra colección—, que devuelve solo los pasajes pertinentes a la consulta en vez de volcar el
artículo entero en cada prompt.
"""

import re
import unicodedata
from typing import Any, Optional

#: Procedencia del corpus. Viaja al prompt para que el contador pueda auditar de dónde salió
#: cada afirmación conceptual sin tener que leer este archivo.
FUENTE = {
    "titulo": "¿Qué es el ReteICA y cuándo se aplica?",
    "editor": "Siigo",
    "url": "https://www.siigo.com/blog/obligaciones-fiscales/que-es-reteica-y-cuando-se-aplica/",
    "naturaleza": "Artículo divulgativo. Conocimiento CONCEPTUAL, no normativo.",
}

#: Advertencia que acompaña a todo el bloque dentro del prompt.
ADVERTENCIA = (
    "CONTEXTO EDUCATIVO. Sirve para entender el tributo, NO para determinar tarifas, bases "
    "mínimas ni municipios. Ninguna cifra de este bloque es aplicable a esta empresa: las "
    "tarifas y bases vinculantes son las de la tabla de ReteICA cargada en Abacus y las del "
    "catálogo de Impuestos. Si la tabla no cubre el caso, declara el faltante; no rellenes el "
    "hueco con una cifra de aquí ni con conocimiento general."
)

#: Corpus curado.
#:
#: Cada pasaje: `id`, `tema`, `texto` (concepto, sin cifras aplicables) y opcionalmente
#: `ejemplo_ilustrativo` (las cifras del artículo, separadas y marcadas). `claves` son los
#: términos por los que el pasaje se recupera.
_PASAJES: tuple[dict[str, Any], ...] = (
    {
        "id": "que_es",
        "tema": "naturaleza del tributo",
        "claves": ("reteica", "ica", "industria", "comercio", "anticipo", "recaudo"),
        "texto": (
            "El ReteICA no es un impuesto adicional: es el mecanismo de recaudo anticipado del "
            "Impuesto de Industria y Comercio (ICA). Quien paga retiene una parte del valor de "
            "la operación y la consigna al municipio a nombre del proveedor, que después la "
            "descuenta de su propio ICA."
        ),
    },
    {
        "id": "quien_retiene",
        "tema": "agente retenedor y sujeto pasivo",
        "claves": (
            "agente",
            "retenedor",
            "sujeto",
            "pasivo",
            "comprador",
            "pagador",
            "proveedor",
            "tercero",
            "entidad",
            "publica",
        ),
        "texto": (
            "Retiene el COMPRADOR o PAGADOR, y solo si el municipio lo designó agente "
            "retenedor de ICA (entidades de derecho público, grandes contribuyentes, "
            "consorcios y comunidades organizadas, entre otros, según cada municipio). El "
            "sujeto pasivo es el proveedor: la persona natural o jurídica que ejerce una "
            "actividad industrial, comercial o de servicios gravada dentro de la jurisdicción "
            "del municipio. Si el comprador no es agente retenedor, no hay retención aunque la "
            "operación esté gravada; si el proveedor no ejerce actividad gravada en esa "
            "jurisdicción, tampoco."
        ),
    },
    {
        "id": "territorialidad",
        "tema": "jurisdicción municipal",
        "claves": (
            "municipio",
            "municipal",
            "jurisdiccion",
            "territorial",
            "ciudad",
            "bogota",
            "medellin",
            "cali",
            "bucaramanga",
            "barranquilla",
            "donde",
        ),
        "texto": (
            "El ICA es un tributo TERRITORIAL: no existe una tarifa nacional. Cada municipio "
            "fija por acuerdo propio quiénes son agentes retenedores, qué tarifas aplican, qué "
            "bases mínimas rigen y en qué casos se practica la retención. Dos operaciones "
            "idénticas en municipios distintos pueden generar retenciones distintas, o una sí y "
            "otra no. Por eso la jurisdicción es un dato imprescindible: sin saber en qué "
            "municipio se causa la operación no se puede determinar la retención."
        ),
    },
    {
        "id": "actividad_economica",
        "tema": "actividad económica / CIIU",
        "claves": (
            "actividad",
            "economica",
            "ciiu",
            "codigo",
            "concepto",
            "servicios",
            "compras",
            "honorarios",
            "comisiones",
            "industrial",
            "comercial",
            "tarifa",
        ),
        "texto": (
            "Dentro de un mismo municipio la tarifa depende de la ACTIVIDAD ECONÓMICA del "
            "proveedor, clasificada por código CIIU o por el concepto de la operación "
            "(servicios, compras, honorarios, comisiones, actividad industrial…). Un municipio "
            "publica una banda de tarifas, no una sola cifra, y la posición dentro de la banda "
            "la determina la actividad. Identificar el concepto de la operación es, por tanto, "
            "un paso previo a buscar la tarifa: no es un detalle de redacción."
        ),
        "ejemplo_ilustrativo": (
            "El artículo cita que en Medellín la tarifa varía entre 0,1 % y 1 % según el "
            "código CIIU. Es un ejemplo del RANGO que puede abarcar un municipio; NO es la "
            "tarifa a aplicar en ningún caso concreto."
        ),
    },
    {
        "id": "base_minima",
        "tema": "bases mínimas",
        "claves": ("base", "minima", "minimo", "tope", "uvt", "cuantia", "cuantias"),
        "texto": (
            "Cada municipio fija su propia base mínima —normalmente expresada en UVT y distinta "
            "para servicios y para compras— por debajo de la cual NO se practica la retención. "
            "No hay uniformidad nacional, ni siquiera aproximada: los topes de una ciudad "
            "pueden ser varias veces los de otra. Comparar la base gravable contra el tope del "
            "municipio correcto es una condición de procedencia, no un refinamiento."
        ),
        "ejemplo_ilustrativo": (
            "El artículo tabula, a modo de ejemplo, bases mínimas de servicios/compras: "
            "Barranquilla 4/27 UVT, Bogotá 4/27 UVT, Bucaramanga 25/50 UVT, Cali 3/15 UVT, "
            "Medellín 15 UVT para cualquier pago. Ilustran la DISPERSIÓN entre municipios; la "
            "base mínima aplicable es la de la fila de la tabla de ReteICA de Abacus."
        ),
    },
    {
        "id": "base_gravable",
        "tema": "base gravable",
        "claves": ("base", "gravable", "subtotal", "iva", "valor", "operacion", "neto"),
        "texto": (
            "La base gravable del ReteICA es el VALOR DE LA OPERACIÓN gravada —el valor de los "
            "bienes o servicios—, no el IVA ni el total facturado. Los tributos que la factura "
            "traiga además (IVA, impoconsumo) no forman parte de esa base. Si la factura mezcla "
            "renglones gravados en el municipio con renglones que no lo están, la base es la de "
            "los renglones sujetos."
        ),
    },
    {
        "id": "calculo",
        "tema": "cálculo y unidades",
        "claves": ("calculo", "calcular", "formula", "tarifa", "porcentaje", "mil", "decimal"),
        "texto": (
            "El cálculo es: ReteICA = base gravable × tarifa. La tarifa se expresa como "
            "porcentaje o por mil según lo publique el municipio, y para operar "
            "aritméticamente se convierte a fracción: una tarifa en porcentaje se divide entre "
            "cien y una publicada por mil entre mil. Esa conversión es un paso MATEMÁTICO y "
            "nada más: no autoriza a reescribir, reinterpretar ni convertir la cifra que está "
            "configurada en la tabla de ReteICA o en el catálogo de Impuestos de Abacus, cuya "
            "unidad ya la fija el sistema, que es además quien hace el cálculo."
        ),
        "ejemplo_ilustrativo": (
            "El artículo desarrolla un servicio de $30.000.000 con tarifa del 0,772 %, que "
            "en decimal es 0,00772: 30.000.000 × 0,00772 = $231.600 de retención, y "
            "$29.768.400 de pago neto al proveedor. Ilustra la ARITMÉTICA y la conversión a "
            "decimal; el 0,772 % no es una tarifa aplicable a esta empresa, a este municipio "
            "ni a esta actividad."
        ),
    },
    {
        "id": "cuando_no_aplica",
        "tema": "cuándo no procede",
        "claves": ("no", "aplica", "excluida", "exenta", "procede", "condiciones", "cuando"),
        "texto": (
            "El ReteICA no es automático. No procede cuando el comprador no es agente "
            "retenedor de ICA en ese municipio, cuando la operación no corresponde a una "
            "actividad gravada en esa jurisdicción, cuando la base gravable no alcanza la base "
            "mínima del municipio, o cuando el acuerdo municipal excluye ese caso. Ante la "
            "ausencia de alguno de esos datos, lo correcto es declarar que falta, no suponerlo."
        ),
    },
    {
        "id": "declaracion",
        "tema": "declaración y periodicidad",
        "claves": (
            "declaracion",
            "declarar",
            "pago",
            "periodicidad",
            "bimestral",
            "calendario",
            "sancion",
        ),
        "texto": (
            "La declaración y el pago del ReteICA retenido siguen el calendario tributario de "
            "cada municipio (en varias ciudades, bimestral). Declarar o pagar fuera de plazo "
            "genera sanciones e intereses. Es contexto del ciclo del tributo; no interviene en "
            "decidir si una factura concreta causa retención."
        ),
    },
)

#: Cuántos pasajes se inyectan como máximo. El corpus completo son nueve; volcarlos todos en
#: cada sugerencia gasta contexto en doctrina que no viene al caso y diluye las tablas
#: vinculantes, que es exactamente lo que la jerarquía de RF-08 intenta evitar.
_MAX_PASAJES = 5

#: Pasajes que entran siempre que ReteICA esté en estudio, con o sin coincidencia de términos.
#: Son los que sostienen las reglas que más se incumplen: que el tributo es territorial, que la
#: tarifa la fija la actividad y que la base mínima la fija el municipio.
_NUCLEO = ("territorialidad", "actividad_economica", "base_minima")

_NO_ALFANUM = re.compile(r"[^a-z0-9]+")


def _normalizar(texto: Any) -> str:
    """Minúsculas sin tildes: 'Jurisdicción' y 'jurisdiccion' deben casar."""
    crudo = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in crudo if unicodedata.category(c) != "Mn").lower()


def _terminos(texto: Any) -> set[str]:
    return {t for t in _NO_ALFANUM.split(_normalizar(texto)) if len(t) > 2}


def recuperar(consulta: str = "", limite: int = _MAX_PASAJES) -> list[dict]:
    """Pasajes conceptuales pertinentes a la operación que se está analizando.

    Se recupera por solapamiento de términos entre la consulta —las descripciones de los
    renglones y el proveedor, la misma que busca los precedentes— y las palabras clave de cada
    pasaje. El núcleo entra siempre: son los conceptos cuya ausencia produjo los fallos que
    motivaron este módulo, y hacerlos depender de que la factura mencione la palabra
    «municipio» significaría que algún día no llegan sin que nadie lo note.

    Devuelve copias, nunca los dicts del corpus: el resultado se serializa al prompt y no debe
    poder mutarse desde fuera.
    """
    if limite <= 0:
        return []
    terminos = _terminos(consulta)

    puntuados = []
    for orden, pasaje in enumerate(_PASAJES):
        nucleo = pasaje["id"] in _NUCLEO
        solape = len(terminos & {t for c in pasaje["claves"] for t in _terminos(c)})
        if not nucleo and not solape:
            continue
        # Orden estable y determinista: núcleo primero, luego por solape, y a igualdad por la
        # posición en el corpus. RF-08 exige que el mismo documento produzca siempre el mismo
        # prompt; un empate resuelto por el azar del hash rompería esa garantía.
        puntuados.append(((0 if nucleo else 1, -solape, orden), pasaje))

    seleccion = [p for _, p in sorted(puntuados, key=lambda kv: kv[0])[:limite]]
    return [
        {
            "id": p["id"],
            "tema": p["tema"],
            "concepto": p["texto"],
            **(
                {"ejemplo_ilustrativo": p["ejemplo_ilustrativo"]}
                if p.get("ejemplo_ilustrativo")
                else {}
            ),
        }
        for p in seleccion
    ]


def bloque_para_prompt(consulta: str = "", limite: int = _MAX_PASAJES) -> Optional[dict]:
    """Sección de evidencia lista para el prompt, o None si no hay nada que aportar."""
    pasajes = recuperar(consulta, limite)
    if not pasajes:
        return None
    return {
        "fuerza": "CONTEXTUAL · EDUCATIVO · NO VINCULANTE · NO es fuente de tarifas",
        "fuente": FUENTE,
        "advertencia": ADVERTENCIA,
        "pasajes": pasajes,
    }
