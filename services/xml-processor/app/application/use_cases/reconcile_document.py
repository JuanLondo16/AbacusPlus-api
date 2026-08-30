"""RF-05 / RF-06: reconciliar un documento con el cerrojo de contabilización puesto.

Un documento queda bloqueado cuando la contabilización terminó sin respuesta legible de
SIIGO: un timeout, un corte de red, un 5xx o un 201 sin identificador. En todos esos casos la
factura de compra **pudo haberse creado**, y como `/v1/purchases` no admite
`Idempotency-Key`, reenviarla crearía un segundo asiento real en la contabilidad del cliente.

El documento se ve en **ERROR**, como cualquier otro fallo —el modelo tiene cinco estados y
ninguno más—, pero con la acción recomendada `VERIFICAR_EN_SIIGO` y con `accounting_locked`
puesto. El cerrojo es lo que convierte esa recomendación en una condición: mientras esté
puesto, ni la cola ni un botón de reintento pueden enviar el documento.

El sistema nunca abre ese cerrojo solo. Este caso de uso es la llave: pregunta a SIIGO qué
tiene y, con esa respuesta, cierra el documento o lo devuelve a la cola.

La operación se divide deliberadamente en dos pasos —consultar y resolver— porque el diseño
exige confirmación humana. El primero no cambia nada; el segundo solo hace lo que el usuario
confirmó tras ver lo que SIIGO respondió.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.domain.exceptions.base import EntityNotFoundException
from app.domain.services.total_verification import verificar_total_contabilizado
from app.domain.value_objects.accounting_error import ErrorClass, RecommendedAction
from app.domain.value_objects.document_status import DocumentStatus

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationView:
    """Lo que SIIGO tiene sobre este documento. No modifica nada."""

    document_id: int
    status: int
    #: True si la consulta a SIIGO se pudo completar. False significa «no se sabe».
    consulted: bool = False
    matches: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    #: Acción que el sistema propone, para que la interfaz la ofrezca al usuario.
    suggested_action: str = "none"
    message: str = ""


@dataclass
class ReconciliationOutcome:
    """Resultado de aplicar la resolución que el usuario confirmó."""

    document_id: int
    status: int
    siigo_id: Optional[str] = None
    siigo_name: Optional[str] = None
    message: str = ""


class ReconcileDocumentUseCase:
    """Consulta y resolución de un documento bloqueado en «Contabilizando»."""

    def __init__(self, document_repo, siigo_client, knowledge_publisher=None):
        self.document_repo = document_repo
        self.siigo_client = siigo_client
        #: RF-08. Cerrar por reconciliación deja el documento igual de contabilizado que el
        #: envío normal, así que debe alimentar el RAG con el mismo criterio.
        self.knowledge_publisher = knowledge_publisher

    # ── Paso 1: consultar (no modifica nada) ───────────────────────────────────

    def lookup(self, document_id: int) -> ReconciliationView:
        """Pregunta a SIIGO si la factura del documento existe.

        No cambia el estado del documento bajo ninguna circunstancia: su única misión es dar
        al contador la información con la que decidir. Cerrar o liberar un documento a partir
        de una consulta automática sería exactamente la clase de automatismo que este
        requisito prohíbe.
        """
        doc = self._documento(document_id)

        if not getattr(doc, "accounting_locked", False):
            return ReconciliationView(
                document_id=document_id,
                status=doc.status,
                message=(
                    "El documento no tiene una contabilización pendiente de verificar, así "
                    "que no hay nada que reconciliar."
                ),
            )

        numero = str(doc.document_number or "").strip()
        if not numero:
            return ReconciliationView(
                document_id=document_id,
                status=doc.status,
                message=(
                    "El documento no tiene número, así que no puede buscarse en SIIGO. "
                    "Verifíquelo manualmente en SIIGO antes de tomar cualquier decisión."
                ),
            )

        lookup = self.siigo_client.find_purchase_invoice(
            provider_invoice_number=numero,
            document_date=doc.date.isoformat() if getattr(doc, "date", None) else None,
        )

        if not lookup.consulted:
            # No se pudo averiguar. Es el único desenlace en el que no se propone nada: dar
            # una recomendación sin datos es peor que no darla.
            return ReconciliationView(
                document_id=document_id,
                status=doc.status,
                consulted=False,
                error=lookup.error,
                suggested_action="none",
                message=(
                    "No se pudo consultar SIIGO. El documento sigue bloqueado; no lo reenvíe "
                    "sin haber comprobado en SIIGO si la factura existe."
                ),
            )

        if lookup.matches:
            return ReconciliationView(
                document_id=document_id,
                status=doc.status,
                consulted=True,
                matches=lookup.matches,
                suggested_action="close",
                message=(
                    "SIIGO ya tiene la factura de este documento. Confirme para cerrarlo con "
                    "ese identificador, sin volver a enviarlo."
                ),
            )

        return ReconciliationView(
            document_id=document_id,
            status=doc.status,
            consulted=True,
            matches=[],
            suggested_action="release",
            message=(
                "SIIGO no tiene ninguna factura para este documento. Confirme para "
                "desbloquearlo y poder contabilizarlo de nuevo."
            ),
        )

    # ── Paso 2: resolver (lo que el usuario confirmó) ──────────────────────────

    def resolve(
        self,
        document_id: int,
        siigo_id: Optional[str],
        siigo_name: Optional[str] = None,
        siigo_total: Optional[float] = None,
    ) -> ReconciliationOutcome:
        """Cierra el documento con el id encontrado, o lo libera si no existe en SIIGO.

        Con `siigo_id` el documento pasa a «Contabilizada» **sin volver a llamar a SIIGO**:
        la factura ya existe y llamar de nuevo es justo lo que se quiere evitar.

        Sin `siigo_id` el documento vuelve a «Error», desde donde puede reenviarse. Esta rama
        se apoya en que el usuario confirmó, tras ver la consulta, que SIIGO no tiene nada:
        es el punto donde el juicio humano asume el riesgo que el sistema no puede asumir
        solo.
        """
        doc = self._documento(document_id)

        if not getattr(doc, "accounting_locked", False):
            raise ValueError(
                "Solo puede reconciliarse un documento con una contabilización pendiente de "
                "verificar. Éste no tiene ninguna."
            )

        if siigo_id:
            # El total que SIIGO informa de la factura ya existente. Viene del `lookup`, que
            # lo consultó para que el contador pudiera decidir — y hasta ahora se descartaba
            # al cerrar. Sin él, un documento cerrado por esta vía quedaba sin total en su
            # ficha de confirmación: era el caso de 2 de los 9 documentos del cliente.
            verificacion = verificar_total_contabilizado(siigo_total, getattr(doc, "total", None))
            actualizado = self.document_repo.mark_accounted(
                document_id,
                siigo_id,
                siigo_name,
                siigo_total=verificacion.total_siigo,
                total_matches_dian=verificacion.coincide,
            )
            if verificacion.comprobado and not verificacion.coincide:
                logger.error(
                    "Reconciliación: el documento %s se cierra con una DIFERENCIA de %.2f. %s",
                    document_id,
                    verificacion.diferencia,
                    verificacion.mensaje,
                )
            logger.info(
                "Reconciliación: documento %s cerrado con el id de SIIGO %s",
                document_id,
                siigo_id,
            )
            # RF-08: la factura consta en SIIGO —lo acaba de comprobar la consulta— y el
            # documento queda en «Contabilizada». Es exactamente la condición que autoriza el
            # aprendizaje, así que este camino genera conocimiento igual que el envío normal.
            #
            # No hay `payload` que pasar porque aquí no se construyó ninguno: el envío
            # original lo hizo y su respuesta se perdió. El publicador reconstruye la
            # causación desde el documento y sus retenciones, que es el estado con el que se
            # envió y que nadie ha podido tocar desde entonces (el documento está bloqueado).
            self._publish_knowledge(document_id, siigo_id, siigo_name)
            return ReconciliationOutcome(
                document_id=document_id,
                status=actualizado.status if actualizado else DocumentStatus.CONTABILIZADA,
                siigo_id=siigo_id,
                siigo_name=siigo_name,
                message="El documento quedó contabilizado con la factura que ya existía en SIIGO.",
            )

        # Se usa `release_accounting_lock` y no `mark_accounting_failed` porque esto no es
        # un fallo nuevo: es la conclusión de una verificación. El historial debe distinguir
        # «SIIGO rechazó esto» de «comprobamos que SIIGO no tenía nada», que es justo lo que
        # un auditor necesita para entender por qué se autorizó un reenvío.
        #
        # El documento queda como corregible y reenviable: es la única transición del sistema
        # que abre el cerrojo, y la hace una persona tras ver lo que SIIGO respondió.
        self.document_repo.release_accounting_lock(
            document_id,
            reason=(
                "Reconciliado manualmente: SIIGO no tenía la factura, el documento se liberó "
                "para volver a contabilizarse."
            ),
            error_class=ErrorClass.CORRECTABLE,
            recommended_action=RecommendedAction.RETRY,
        )
        logger.info("Reconciliación: documento %s liberado para reenvío", document_id)
        return ReconciliationOutcome(
            document_id=document_id,
            status=DocumentStatus.ERROR,
            message="El documento se desbloqueó y puede contabilizarse de nuevo.",
        )

    # ── Auxiliar ───────────────────────────────────────────────────────────────

    def _publish_knowledge(
        self, document_id: int, siigo_id: str, siigo_name: Optional[str]
    ) -> None:
        """RF-08: indexa la causación, sin que un fallo del RAG afecte a la reconciliación."""
        if self.knowledge_publisher is None:
            return
        try:
            self.knowledge_publisher.publish(
                document_id=document_id, siigo_id=siigo_id, siigo_name=siigo_name
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "RF-08: fallo al generar el conocimiento del documento %s tras reconciliar",
                document_id,
            )

    def _documento(self, document_id: int):
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise EntityNotFoundException("Document", str(document_id))
        return doc
