"""RF-05: la cola de contabilización.

Encolar es la única operación que hace la petición HTTP del usuario. Devuelve un
identificador de lote de inmediato y el trabajo real lo hacen los workers, en segundo plano.

Por qué encolar en vez de contabilizar dentro de la petición
-------------------------------------------------------------
La versión anterior recorría el lote dentro del propio `POST`: cincuenta documentos a unos
dos segundos cada uno mantenían la conexión abierta más de un minuto y medio. Eso tiene dos
consecuencias, y la segunda es la grave:

1. Cualquier proxy intermedio puede cortar una petición tan larga, y el usuario ve un error
   sobre un lote que en realidad siguió ejecutándose.
2. Si el proceso muere a mitad, los documentos ya enviados no dejan ningún registro de que
   se enviaron. Nadie sabe cuáles llegaron a SIIGO, y averiguarlo obliga a revisar factura
   por factura — o, peor, invita a reenviarlas.

Con la cola persistida, el trabajo sobrevive al reinicio con su cerrojo y su historial
intactos, y el progreso se consulta cuando se quiera.

Sobre la estrategia de concurrencia
------------------------------------
La cola no la fija: la lee de la configuración. Arranca con un worker —equivalente al
comportamiento secuencial anterior— porque SIIGO documenta un límite de peticiones por
minuto pero **no** documenta ningún límite de concurrencia, y suponer que tolera N
peticiones simultáneas sin haberlo comprobado es la clase de suposición que produce
respuestas ambiguas. Subir la concurrencia es cambiar `ACCOUNTING_MAX_CONCURRENCY`, y debe
apoyarse en las pruebas contra el ambiente real.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.config.accounting_settings import (
    AccountingSettings,
    get_accounting_settings,
)

logger = logging.getLogger(__name__)


@dataclass
class EnqueueResult:
    """Qué se encoló y qué se rechazó, documento por documento."""

    batch_id: str
    enqueued: list = field(default_factory=list)
    #: Documentos que no se encolaron, con el motivo. No es un error del lote: es
    #: información que el usuario necesita para saber qué quedó fuera y por qué.
    rejected: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.enqueued) + len(self.rejected)


class AccountingQueueService:
    """Alta de trabajos y consulta de progreso. No habla con SIIGO."""

    def __init__(
        self,
        document_repo,
        job_repo,
        settings: Optional[AccountingSettings] = None,
    ):
        self.document_repo = document_repo
        self.job_repo = job_repo
        self.settings = settings or get_accounting_settings()

    def enqueue(
        self,
        document_ids: list,
        *,
        enqueued_by: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> EnqueueResult:
        """Encola documentos para contabilizar. Nunca lanza por un documento inelegible.

        La elegibilidad se comprueba aquí de forma **preliminar**: sirve para dar un mensaje
        útil de inmediato, no para autorizar el envío. La autorización real la da
        `claim_for_accounting` en el momento de enviar, bajo bloqueo de fila, porque entre
        encolar y enviar el documento pudo cambiar. Duplicar la comprobación es deliberado:
        la de aquí es por cortesía, la de allí es la que protege.
        """
        if len(document_ids) > self.settings.batch_max_size:
            raise ValueError(
                f"El lote supera el máximo de {self.settings.batch_max_size} documentos por "
                "envío. Divida la selección."
            )

        resultado = EnqueueResult(batch_id=batch_id or uuid.uuid4().hex)

        for document_id in document_ids:
            motivo = self._motivo_de_rechazo(document_id)
            if motivo is not None:
                resultado.rejected.append({"document_id": document_id, "reason": motivo})
                continue

            job = self.job_repo.enqueue(
                document_id,
                max_attempts=self.settings.max_attempts,
                batch_id=resultado.batch_id,
                enqueued_by=enqueued_by,
            )
            if job is None:
                # El índice único rechazó el alta: ya había un trabajo activo. No es un
                # error — es exactamente la protección funcionando ante un doble clic.
                resultado.rejected.append(
                    {
                        "document_id": document_id,
                        "reason": "El documento ya está en la cola de contabilización.",
                    }
                )
                continue

            resultado.enqueued.append({"document_id": document_id, "job_id": job.id})

        logger.info(
            "RF-05: lote %s encolado — %s aceptados, %s rechazados",
            resultado.batch_id,
            len(resultado.enqueued),
            len(resultado.rejected),
        )
        return resultado

    def _motivo_de_rechazo(self, document_id: int) -> Optional[str]:
        """Por qué este documento no puede encolarse, o None si sí puede."""
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            return "El documento no existe."
        if doc.status == DocumentStatus.CONTABILIZADA:
            return "El documento ya está contabilizado en SIIGO."
        if getattr(doc, "accounting_locked", False):
            # El caso que más importa acertar. Un documento bloqueado tiene un envío cuyo
            # desenlace se desconoce: encolarlo sería programar un duplicado.
            return (
                "El documento tiene una contabilización sin desenlace conocido. Verifique "
                "en SIIGO si la factura ya existe antes de volver a enviarlo."
            )
        if doc.status == DocumentStatus.APROBADO:
            return None
        if doc.status == DocumentStatus.ERROR and doc.accounting_error:
            return None
        return (
            "El documento debe estar aprobado, o con un error de contabilización, para "
            "poder enviarse."
        )

    def progress(self, batch_id: str) -> dict:
        """Progreso de un lote, para la barra de la interfaz."""
        return self.job_repo.batch_progress(batch_id)

    def cancel(self, job_id: int) -> bool:
        """Cancela un trabajo que aún no ha salido hacia SIIGO."""
        return self.job_repo.cancel(job_id)
