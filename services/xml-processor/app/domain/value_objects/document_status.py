"""Estados funcionales del documento.

Son cinco y solo cinco:

    PROCESADO → CAUSADO → APROBADO → CONTABILIZADA
                                   ↘ ERROR

`ERROR` representa **cualquier** fallo de contabilización. Lo que distingue un fallo de otro
no es el estado sino la *clasificación* del error, que vive en
`documents.accounting_error_class` / `accounting_recommended_action` y decide qué acción se
le ofrece al contador (ver `domain/services/siigo_error_classifier`).

Sobre el cerrojo de contabilización
-----------------------------------
Hubo aquí un sexto estado, `CONTABILIZANDO = 350`, que servía de cerrojo mientras se hablaba
con SIIGO. La necesidad que cubría es real y no ha desaparecido: la API de SIIGO no ofrece
idempotencia en `/v1/purchases` —su documentación habilita `Idempotency-Key` solo en
/v1/invoices, /v1/credit-notes, /v1/journals y /v1/vouchers—, así que reenviar un documento
cuyo desenlace no se conoce puede crear una segunda factura de compra real.

Lo que cambia es dónde vive esa protección. El cerrojo pasa a ser una columna booleana,
`documents.accounting_locked`, en lugar de un estado: es un dato **interno de la cola**, no
una etapa del ciclo de vida contable que el contador deba interpretar. Un documento cuyo
envío está en curso o quedó en desenlace incierto se ve como `ERROR` con la acción
`VERIFICAR_EN_SIIGO`, y el cerrojo sigue impidiendo exactamente los mismos reenvíos que
antes: el doble clic, las dos pestañas, los dos usuarios y el reintento tras un timeout.

La protección no se ha debilitado en ningún punto; se ha movido de la columna `status` a una
columna propia, que es donde corresponde a un detalle de implementación de la cola.
"""


class DocumentStatus:
    ERROR = 0
    PROCESADO = 100
    CAUSADO = 200
    APROBADO = 300
    CONTABILIZADA = 400

    NAMES = {
        0: "Error",
        100: "Procesado",
        200: "Causado",
        300: "Aprobado",
        400: "Contabilizada",
    }

    ALL = frozenset(NAMES)

    # Estados en los que el contador todavía puede ajustar la imputación del documento:
    # cuenta PUC por línea (RF-01), tipo de pago, centro de costo (RF-07) y retenciones.
    #
    # Causado SÍ es editable: causar significa que la contabilización ya se calculó, no que
    # esté cerrada. El contador revisa lo que propuso el modelo y lo corrige antes de
    # aprobar — ése es justamente el momento en que más edita.
    #
    # Aprobado y Contabilizada quedan fuera: aprobar es el acto por el que el contador se
    # hace responsable de la imputación, y permitir editarla después la cambiaría sin dejar
    # rastro ni exigir una nueva aprobación.
    #
    # ERROR no está en esta lista pero **puede** ser editable, y por eso existe
    # `is_editable_document`: depende de POR QUÉ está en error. Ver ese método.
    EDITABLE = frozenset({PROCESADO, CAUSADO})

    @classmethod
    def is_editable(cls, status) -> bool:
        """True si el estado, por sí solo, admite cambios en la imputación contable.

        Se conserva para los sitios que solo tienen el código de estado a mano. Para un
        documento en ERROR devuelve False, que es el comportamiento seguro por defecto: quien
        quiera autorizar la corrección de un error de contabilización debe usar
        `is_editable_document`, que mira el motivo del error y no solo el estado.
        """
        try:
            return int(status) in cls.EDITABLE
        except (TypeError, ValueError):
            return False

    @classmethod
    def is_editable_document(cls, doc) -> bool:
        """True si ESTE documento admite cambios en su imputación contable.

        Añade a la regla de estado el caso que RF-05 exige: **editar y reintentar**. Cuando
        SIIGO rechaza un dato contable —una cuenta PUC inexistente o inactiva, un centro de
        costo, un impuesto o una retención inválidos— el documento queda en ERROR, y la
        corrección de ese dato es justamente la acción que se le pide al contador. Sin esta
        excepción, el flujo «Error → Editar → Reintentar» sería imposible: el documento
        quedaría en un error que nadie puede arreglar.

        La apertura está acotada por tres condiciones que se exigen a la vez, y ninguna sobra:

        1. **El estado es ERROR.** Los demás estados siguen la regla de siempre.
        2. **El error es de contabilización** (`accounting_error` no nulo). Distingue el
           documento que falló al contabilizar —y que por tanto ya pasó por la aprobación del
           contador, con una imputación revisada— del que nació en ERROR porque su XML no se
           pudo procesar. Ese segundo no tiene una imputación coherente que ajustar.
        3. **El error es de los corregibles** (acción `EDITAR_Y_REINTENTAR`). Un fallo de red
           o un desenlace incierto no se arreglan editando la causación, y abrir la edición
           ahí solo invitaría a tocar un documento que quizá ya está contabilizado en SIIGO.

        El cerrojo se comprueba aparte, en el envío: aquí se decide si se puede *editar*, no
        si se puede *enviar*. Son permisos distintos y conviene que no se confundan.
        """
        if doc is None:
            return False

        try:
            status = int(getattr(doc, "status", None))
        except (TypeError, ValueError):
            return False

        if status in cls.EDITABLE:
            return True
        if status != cls.ERROR:
            return False
        if not getattr(doc, "accounting_error", None):
            return False

        # Import local: el value object de estados es la base del dominio y no debe depender
        # de la taxonomía de errores en tiempo de carga.
        from app.domain.value_objects.accounting_error import RecommendedAction

        return getattr(doc, "accounting_recommended_action", None) == (
            RecommendedAction.EDIT_AND_RETRY
        )
