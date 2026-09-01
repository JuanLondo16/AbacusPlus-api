"""RF-08 · Semilla de criterios de retención para un tenant nuevo.

Mismo papel que `retention_fuente_seed.py` en el xml-processor: un punto de partida que se
carga UNA vez, al aprovisionar, y a partir de ahí vive como dato editable en la base del
cliente. No es la fuente de verdad en tiempo de ejecución —esa es la tabla
`retention_criteria`—, solo evita que un tenant recién creado arranque sin ningún criterio.

El contenido proviene del cuestionario «Preguntas Retenciones» que respondió el contador de
IKBO el 10 de agosto de 2026. Se conserva la pregunta junto a cada respuesta porque un
criterio suelto pierde su alcance: «por el municipio» solo significa algo al lado de «¿cómo
se determina si aplica ReteICA?».

IMPORTANTE (para el contador): estas respuestas son de UN contador y deben revisarse en cada
empresa. El seed es no destructivo —si el tenant ya tiene criterios, no se toca nada—, así
que corregirlos aquí no reescribe los de nadie: se editan por la API del servicio.
"""

FUENTE_POR_DEFECTO = "Cuestionario «Preguntas Retenciones» respondido por el contador (2026-08-10)"

#: (tema, pregunta, criterio)
CRITERIOS_POR_DEFECTO: list[dict] = [
    # ── ReteICA ───────────────────────────────────────────────────────────────
    {
        "tema": "reteica",
        "pregunta": "¿Cómo determinar si una operación está sujeta a ReteICA?",
        "criterio": "Por el municipio donde se haya generado la operación.",
    },
    {
        "tema": "reteica",
        "pregunta": "¿El municipio de la factura basta para determinar si aplica ReteICA?",
        "criterio": (
            "Puede bastar, pero depende de si el proveedor tiene sucursales en otros "
            "municipios. Si hay duda sobre dónde se prestó el servicio, es un caso de "
            "criterio del contador."
        ),
    },
    {
        "tema": "reteica",
        "pregunta": "¿Cómo se determina la tarifa y la base de ReteICA?",
        "criterio": (
            "La tarifa está dada por el CONCEPTO de la operación: compra, servicios, "
            "honorarios, comisiones o servicios profesionales."
        ),
    },
    # ── ReteIVA ───────────────────────────────────────────────────────────────
    {
        "tema": "reteiva",
        "pregunta": "¿Qué condiciones deben cumplirse para que aplique ReteIVA?",
        "criterio": (
            "Que la operación genere IVA y que el agente retenedor esté obligado a retener "
            "IVA o pertenezca al Régimen Simple de Tributación."
        ),
    },
    {
        "tema": "reteiva",
        "pregunta": "¿Qué se verifica del retenedor y del proveedor?",
        "criterio": "La responsabilidad fiscal y el régimen de cada uno.",
    },
    {
        "tema": "reteiva",
        "pregunta": "¿Sobre qué base y con qué porcentaje se calcula?",
        "criterio": (
            "La base es el IVA de la factura. La tarifa que aplica esta empresa es el 15% "
            "sobre el valor del IVA."
        ),
    },
    # ── Autorretención ────────────────────────────────────────────────────────
    {
        "tema": "autorretencion",
        "pregunta": "¿Cuándo practica la empresa autorretención de renta?",
        "criterio": (
            "Cuando está acogida al artículo 114-1 del Estatuto Tributario. Todos los "
            "ingresos quedan sujetos al cálculo del anticipo de autorretención."
        ),
    },
    {
        "tema": "autorretencion",
        "pregunta": "¿Qué ocurre si el proveedor también es autorretenedor?",
        "criterio": (
            "La autorretención de la empresa se calcula sobre sus VENTAS, no sobre las "
            "compras, así que no altera la causación de una factura de compra. Cosa distinta "
            "es que el PROVEEDOR sea autorretenedor de renta: en ese caso no se le practica "
            "ReteFuente."
        ),
    },
    # ── ReteFuente ────────────────────────────────────────────────────────────
    {
        "tema": "retefuente",
        "pregunta": "¿Cómo se determina el concepto de ReteFuente de una operación?",
        "criterio": (
            "Por el concepto que viene en el documento emitido por el proveedor: "
            "concretamente el nombre del producto o la descripción de la línea."
        ),
    },
    {
        "tema": "retefuente",
        "pregunta": "¿Qué condiciones del proveedor cambian la tarifa o impiden retener?",
        "criterio": (
            "El cambio de régimen (de ordinario a Simple), la responsabilidad fiscal, y que "
            "sea autorretenedor o gran contribuyente autorretenedor."
        ),
    },
    {
        "tema": "retefuente",
        "pregunta": "¿Cuál es la principal excepción antes de aplicar ReteFuente?",
        "criterio": (
            "Una empresa de régimen común NO puede practicar retención en la fuente a un "
            "autorretenedor ni a un gran contribuyente autorretenedor."
        ),
    },
    # ── Proceso general de decisión ───────────────────────────────────────────
    {
        "tema": "proceso",
        "pregunta": "¿Qué información se necesita para decidir?",
        "criterio": "Del proveedor y del comprador: régimen, responsabilidad fiscal y ubicación.",
    },
    {
        "tema": "proceso",
        "pregunta": "¿Cómo se determina que una retención NO aplica?",
        "criterio": "Por el régimen y la responsabilidad fiscal de las partes.",
    },
    {
        "tema": "proceso",
        "pregunta": "¿Pueden coexistir ReteFuente, ReteICA y ReteIVA en una misma factura?",
        "criterio": (
            "Sí. ReteFuente y ReteICA comparten base —el valor bruto de la operación—; "
            "ReteIVA se calcula sobre el IVA."
        ),
    },
    {
        "tema": "proceso",
        "pregunta": "¿Qué retenciones no pueden coexistir?",
        "criterio": (
            "Un tercero puede ser autorretenedor de renta y no serlo de ICA o IVA, y "
            "viceversa. La condición se verifica por separado para cada tipo: ser "
            "autorretenedor de uno no exime de los demás."
        ),
    },
    {
        "tema": "proceso",
        "pregunta": "¿Cuándo requiere la factura criterio de un contador?",
        "criterio": "Cuando supera los topes de retención.",
    },
    {
        "tema": "proceso",
        "pregunta": "¿Qué genera más errores al determinar retenciones?",
        "criterio": (
            "Los conceptos o descripciones de la factura: es donde se equivoca la "
            "clasificación. Ante una descripción ambigua conviene abstenerse antes que "
            "elegir un concepto por aproximación."
        ),
    },
]
