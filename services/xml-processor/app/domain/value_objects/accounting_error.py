"""RF-05: taxonomía de los fallos de contabilización.

El estado funcional del documento sigue siendo **ERROR** en todos los casos. Lo que cambia
según el fallo no es el estado, sino **qué puede hacer el usuario a continuación**, y eso es
lo que modelan estas dos enumeraciones.

La separación entre las dos es deliberada y hace trabajo real:

- `ErrorClass` responde «¿qué naturaleza tiene el fallo?». Es la etiqueta técnica, la que se
  audita y con la que se hacen estadísticas.
- `RecommendedAction` responde «¿qué se puede hacer con este documento?». Es interna.

**Nada de esto se le muestra al usuario.** El contador ve el estado —ERROR— y el mensaje de
lo que ocurrió, y en la columna de acciones ve dos botones, activos o no. Las capacidades
`can_edit` y `can_retry`, al final de este módulo, son la frontera: todo lo de arriba se
queda dentro, y hacia la pantalla solo cruzan dos booleanos.

Esa frontera es lo que hace la estructura escalable. Distinguir internamente un timeout de
una cuenta PUC inválida es obligatorio —de esa distinción depende que no se dupliquen
asientos contables—, pero convertirla en algo que el usuario tenga que entender solo añade
vocabulario a una pantalla donde lo único accionable es «lo corrijo» o «lo reintento». Una
clase de error nueva se mapea a un par de booleanos y no cambia ni el contrato de la API ni
el frontend.
"""


class ErrorClass:
    """Naturaleza técnica del fallo. Se audita; no se muestra como tal al contador."""

    #: Fallo pasajero del que consta que SIIGO NO creó nada. Reintentar sin cambiar nada
    #: tiene sentido: `service_unavailable` (503), corte de red antes de enviar.
    TRANSIENT = "TRANSIENT"

    #: `requests_limit` (429). Es reintentable, pero solo tras esperar: repetir de inmediato
    #: reproduce el error y suma a la proporción de errores de la cuenta.
    RATE_LIMIT = "RATE_LIMIT"

    #: **No se sabe si SIIGO creó el comprobante.** Timeout, 5xx, 408, 2xx sin identificador.
    #: La clase más importante de todas: es la única en la que reintentar puede duplicar un
    #: asiento contable real, porque /v1/purchases no admite `Idempotency-Key`.
    UNCERTAIN = "UNCERTAIN"

    #: SIIGO afirma que el comprobante ya existe (`duplicated_document`). No es un fallo:
    #: es la contabilización que se buscaba, ya hecha. Se cierra reconciliando, no reenviando.
    DUPLICATE = "DUPLICATE"

    #: Dato contable rechazado por SIIGO: cuenta PUC inexistente o inactiva, centro de costo,
    #: impuesto, retención o tercero inválidos. Consta que SIIGO no creó nada.
    CORRECTABLE = "CORRECTABLE"

    #: Problema de configuración o credenciales, no del documento: `unauthorized`,
    #: `invalid_partner_id`, plantilla de parámetros ausente. Corregirlo no es tarea del
    #: contador sobre este documento, sino sobre la integración.
    CONFIG = "CONFIG"

    #: No clasificable. Nunca se reintenta solo: un fallo que no entendemos no puede
    #: presumirse inocuo, y presumirlo es lo que crea duplicados.
    UNKNOWN = "UNKNOWN"


class RecommendedAction:
    """Lo que el sistema autoriza al usuario a hacer. Es lo que el frontend interpreta."""

    #: Reenviar tal cual, sin tocar la causación. La cola puede hacerlo sola.
    RETRY = "REINTENTAR"

    #: Abrir la causación, corregir el dato rechazado y volver a enviarla.
    EDIT_AND_RETRY = "EDITAR_Y_REINTENTAR"

    #: Consultar en SIIGO si la factura existe ANTES de permitir cualquier reenvío. Es la
    #: acción de los desenlaces inciertos, y la única defensa real contra la doble
    #: contabilización cuando la respuesta se perdió.
    RECONCILE = "VERIFICAR_EN_SIIGO"

    #: Corregir credenciales o configuración de la integración; el documento está bien.
    FIX_CONFIGURATION = "REVISAR_CONFIGURACION"

    #: Mostrar el error y no ofrecer reintento automático.
    MANUAL_REVIEW = "REVISION_MANUAL"


#: Acciones desde las que un reenvío es seguro sin verificar antes en SIIGO.
#:
#: La lista es corta y debe seguir siéndolo. Cada entrada afirma «consta que SIIGO no creó
#: el comprobante», y esa afirmación es la que autoriza a volver a llamar a /v1/purchases.
#: `RECONCILE` queda fuera por definición; `MANUAL_REVIEW`, porque no consta nada.
SAFE_TO_RESEND_ACTIONS = frozenset(
    {
        RecommendedAction.RETRY,
        RecommendedAction.EDIT_AND_RETRY,
        RecommendedAction.FIX_CONFIGURATION,
    }
)

#: Clases cuyo reintento puede hacer la cola sola, sin intervención humana.
#:
#: `CORRECTABLE` NO está: repetir la misma petición con los mismos datos volvería a fallar
#: igual y solo gastaría cupo del límite por minuto. Necesita que alguien edite primero.
AUTO_RETRYABLE_CLASSES = frozenset({ErrorClass.TRANSIENT, ErrorClass.RATE_LIMIT})


def is_safe_to_resend(action: str) -> bool:
    """True si el documento puede volver a enviarse a SIIGO sin verificar antes."""
    return action in SAFE_TO_RESEND_ACTIONS


def is_auto_retryable(error_class: str) -> bool:
    """True si la cola puede reintentar sola, sin intervención humana."""
    return error_class in AUTO_RETRYABLE_CLASSES


def requires_reconciliation(error_class: str) -> bool:
    """True si hay que preguntarle a SIIGO qué pasó antes de tocar el documento."""
    return error_class in (ErrorClass.UNCERTAIN, ErrorClass.DUPLICATE)


# ── Capacidades: lo único que el usuario ve ────────────────────────────────────
#
# La interfaz no muestra clases de error ni acciones recomendadas. Muestra el estado (ERROR),
# el mensaje de lo que pasó, y dos botones que están activos o no.
#
# Estas dos funciones son la frontera entre la estructura técnica interna —que sí distingue
# un timeout de una cuenta PUC inválida, porque tiene que hacerlo para no duplicar asientos—
# y lo que llega a la pantalla, que son dos booleanos. Añadir mañana una clase de error nueva
# significa mapearla aquí a un par de booleanos: ni el contrato de la API ni el frontend
# cambian.


def can_edit(action: str) -> bool:
    """True si corregir la causación es lo que desatasca este documento.

    Se limita a los errores en los que SIIGO rechazó un dato contable. En un desenlace
    incierto la edición queda cerrada a propósito: ese documento puede estar ya contabilizado
    en SIIGO, y editarle la causación crearía una discrepancia silenciosa entre lo que Abacus
    cree que se envió y lo que SIIGO tiene registrado.
    """
    return action == RecommendedAction.EDIT_AND_RETRY


def can_retry(action: str) -> bool:
    """True si el documento puede volver a enviarse a la cola.

    Cubre el reintento simple y el reintento posterior a una corrección: en los dos casos
    consta que SIIGO no creó el comprobante, que es la única condición que autoriza un nuevo
    envío. Un `VERIFICAR_EN_SIIGO` devuelve False, y ése es el punto entero de la función:
    mientras no se sepa si la factura existe, ningún camino de la aplicación puede reenviarla.
    """
    return action in SAFE_TO_RESEND_ACTIONS
