"""RF-05: acceso a la cola de contabilización y a su historial.

La operación delicada de este módulo es `claim_next`. Todo lo demás son escrituras
ordinarias; ésa es la que decide qué worker toca qué trabajo, y hacerla mal significa dos
workers enviando la misma factura a SIIGO.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.accounting import (
    AccountingAttempt,
    AccountingJob,
    DocumentFieldChange,
    JobState,
)

logger = logging.getLogger(__name__)


class AccountingJobRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Encolado ───────────────────────────────────────────────────────────────

    def enqueue(
        self,
        document_id: int,
        *,
        max_attempts: int,
        batch_id: Optional[str] = None,
        enqueued_by: Optional[str] = None,
    ) -> Optional[AccountingJob]:
        """Crea un trabajo para el documento. Devuelve None si ya tenía uno activo.

        El «ya tenía uno activo» no se resuelve consultando antes y creando después: entre la
        consulta y la creación caben dos peticiones simultáneas y las dos verían la vía
        libre. Se intenta insertar y se deja que el índice único parcial
        `uq_accounting_jobs_active` sea quien arbitre. La base de datos es el único árbitro
        que no tiene condiciones de carrera.
        """
        job = AccountingJob(
            document_id=document_id,
            batch_id=batch_id,
            state=JobState.PENDING,
            attempt=0,
            max_attempts=max_attempts,
            next_attempt_at=datetime.now(timezone.utc),
            enqueued_by=enqueued_by,
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            logger.info(
                "RF-05: el documento %s ya tiene un trabajo de contabilización activo",
                document_id,
            )
            return None
        self.db.refresh(job)
        return job

    def get(self, job_id: int) -> Optional[AccountingJob]:
        return self.db.query(AccountingJob).filter(AccountingJob.id == job_id).first()

    def get_active_for_document(self, document_id: int) -> Optional[AccountingJob]:
        return (
            self.db.query(AccountingJob)
            .filter(
                AccountingJob.document_id == document_id,
                AccountingJob.state.in_(tuple(JobState.ACTIVE)),
            )
            .first()
        )

    def get_batch(self, batch_id: str) -> list:
        return (
            self.db.query(AccountingJob)
            .filter(AccountingJob.batch_id == batch_id)
            .order_by(AccountingJob.id)
            .all()
        )

    # ── Toma de trabajo ────────────────────────────────────────────────────────

    def claim_next(self, worker_id: str, *, stale_after_seconds: int) -> Optional[AccountingJob]:
        """Toma el siguiente trabajo ejecutable, en exclusiva. None si no hay ninguno.

        `SELECT ... FOR UPDATE SKIP LOCKED` es la pieza central. `FOR UPDATE` impide que dos
        workers se lleven la misma fila; `SKIP LOCKED` hace que el segundo worker, en lugar
        de esperar a que el primero suelte la fila, pase a la siguiente. Sin `SKIP LOCKED` la
        concurrencia configurada sería decorativa: los N workers harían cola sobre el mismo
        trabajo y avanzarían de uno en uno.

        Se recogen también los trabajos **huérfanos**: los que quedaron en RUNNING porque el
        proceso que los tenía murió. Se identifican por llevar más de `stale_after_seconds`
        tomados, un umbral que debe superar con holgura al timeout de SIIGO para no confundir
        una llamada lenta con un worker muerto.

        Rescatar un huérfano NO significa reenviarlo. Se devuelve a la cola, y el desenlace
        de su envío interrumpido lo decide el mismo camino que cualquier otro: si el
        documento quedó con el cerrojo puesto, `claim_for_accounting` lo rechazará y acabará
        en reconciliación. Reintentarlo directamente sería justo el atajo que crea duplicados.
        """
        ahora = datetime.now(timezone.utc)
        limite_huerfano = ahora - timedelta(seconds=stale_after_seconds)

        job = (
            self.db.query(AccountingJob)
            .filter(
                or_(
                    (AccountingJob.state == JobState.PENDING)
                    & (
                        AccountingJob.next_attempt_at.is_(None)
                        | (AccountingJob.next_attempt_at <= ahora)
                    ),
                    (AccountingJob.state == JobState.RUNNING)
                    & (AccountingJob.locked_at < limite_huerfano),
                )
            )
            .order_by(AccountingJob.next_attempt_at.nullsfirst(), AccountingJob.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            self.db.rollback()
            return None

        if job.state == JobState.RUNNING:
            logger.warning(
                "RF-05: se rescata el trabajo %s (documento %s), tomado por %s y sin "
                "terminar desde %s",
                job.id,
                job.document_id,
                job.locked_by,
                job.locked_at,
            )

        job.state = JobState.RUNNING
        job.locked_by = worker_id
        job.locked_at = ahora
        self.db.commit()
        self.db.refresh(job)
        return job

    # ── Desenlaces ─────────────────────────────────────────────────────────────

    def mark_succeeded(
        self, job_id: int, *, siigo_id: str, siigo_name: Optional[str] = None
    ) -> None:
        self._finalizar(
            job_id,
            state=JobState.SUCCEEDED,
            siigo_id=siigo_id,
            siigo_name=siigo_name,
            error_class=None,
            recommended_action=None,
            last_error=None,
        )

    def mark_failed(
        self,
        job_id: int,
        *,
        error: str,
        error_class: Optional[str],
        recommended_action: Optional[str],
        error_code: Optional[str] = None,
        http_status: Optional[int] = None,
        needs_reconciliation: bool = False,
        attempt: Optional[int] = None,
    ) -> None:
        """Cierra el trabajo sin éxito.

        `needs_reconciliation` lo lleva a un estado terminal distinto del fallo normal. La
        distinción es operativa y no cosmética: un `FAILED` es un documento que alguien puede
        corregir y reenviar, mientras que un `NEEDS_RECONCILIATION` es un documento del que
        no se sabe si ya está en SIIGO, y esos hay que vigilarlos como grupo aparte.
        """
        campos: dict[str, Any] = {
            "error_class": error_class,
            "recommended_action": recommended_action,
            "last_error": error,
            "last_error_code": error_code,
            "last_http_status": http_status,
        }
        # El número de intento se persiste también al cerrar. Sin esto un trabajo agotado
        # quedaba registrado con `attempt = 0`, y esa cifra es la que mira quien decide si
        # reintentar a mano: decía que no se había intentado nunca.
        if attempt is not None:
            campos["attempt"] = attempt

        self._finalizar(
            job_id,
            state=(
                JobState.NEEDS_RECONCILIATION if needs_reconciliation else JobState.FAILED
            ),
            **campos,
        )

    def reschedule(
        self,
        job_id: int,
        *,
        next_attempt_at: datetime,
        attempt: int,
        error: str,
        error_class: Optional[str],
        recommended_action: Optional[str],
        error_code: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:
        """Devuelve el trabajo a la cola con su backoff aplicado."""
        job = self.get(job_id)
        if job is None:
            return
        job.state = JobState.PENDING
        job.attempt = attempt
        job.next_attempt_at = next_attempt_at
        job.last_attempt_at = datetime.now(timezone.utc)
        job.last_error = (error or "")[:4000]
        job.error_class = error_class
        job.recommended_action = recommended_action
        job.last_error_code = error_code
        job.last_http_status = http_status
        # Se suelta el worker: el trabajo vuelve a estar disponible para cualquiera.
        job.locked_by = None
        job.locked_at = None
        self.db.commit()

    def cancel(self, job_id: int) -> bool:
        """Cancela un trabajo que todavía no ha salido hacia SIIGO.

        Solo desde PENDING. Un trabajo en RUNNING ya puede tener una petición en vuelo, y
        cancelarlo dejaría el documento marcado como cancelado mientras SIIGO crea la
        factura — precisamente el tipo de mentira que hace falta evitar.
        """
        job = self.get(job_id)
        if job is None or job.state != JobState.PENDING:
            return False
        job.state = JobState.CANCELLED
        self.db.commit()
        return True

    def _finalizar(self, job_id: int, *, state: str, **campos: Any) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.state = state
        job.last_attempt_at = datetime.now(timezone.utc)
        job.locked_by = None
        job.locked_at = None
        job.next_attempt_at = None
        for campo, valor in campos.items():
            if campo == "last_error" and valor is not None:
                valor = str(valor)[:4000]
            setattr(job, campo, valor)
        self.db.commit()

    # ── Métricas del lote ──────────────────────────────────────────────────────

    def batch_progress(self, batch_id: str) -> dict:
        """Resumen de un lote para la barra de progreso.

        Se calcula sobre las filas del lote y no sobre un contador incremental: un contador
        se desincroniza en cuanto un proceso muere a mitad, y entonces la barra de progreso
        miente sin que nada lo delate.
        """
        jobs = self.get_batch(batch_id)
        resumen = {
            "batch_id": batch_id,
            "total": len(jobs),
            "pending": 0,
            "running": 0,
            "successful": 0,
            "failed": 0,
            "needs_reconciliation": 0,
            "cancelled": 0,
        }
        mapa = {
            JobState.PENDING: "pending",
            JobState.RUNNING: "running",
            JobState.SUCCEEDED: "successful",
            JobState.FAILED: "failed",
            JobState.NEEDS_RECONCILIATION: "needs_reconciliation",
            JobState.CANCELLED: "cancelled",
        }
        for job in jobs:
            clave = mapa.get(job.state)
            if clave:
                resumen[clave] += 1
        resumen["finished"] = (
            resumen["successful"]
            + resumen["failed"]
            + resumen["needs_reconciliation"]
            + resumen["cancelled"]
        )
        resumen["done"] = resumen["finished"] == resumen["total"]
        return resumen


class AccountingAuditRepository:
    """Escritura del historial. Solo inserta: nada de este historial se modifica jamás."""

    def __init__(self, db: Session):
        self.db = db

    def record_attempt(
        self,
        *,
        document_id: int,
        job_id: Optional[int],
        attempt: int,
        started_at: datetime,
        finished_at: Optional[datetime] = None,
        request_payload: Optional[dict] = None,
        response_body: Optional[dict] = None,
        http_status: Optional[int] = None,
        ok: bool = False,
        siigo_id: Optional[str] = None,
        siigo_name: Optional[str] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        error_class: Optional[str] = None,
        recommended_action: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ) -> Optional[AccountingAttempt]:
        """Registra un intento.

        Devuelve None y registra un warning si la escritura falla, en lugar de propagar. Es
        la única concesión de este módulo, y está pensada: perder una línea de auditoría es
        malo, pero tumbar la contabilización de un documento porque el historial no se pudo
        escribir sería peor —y dejaría además al documento en un limbo peor auditado todavía—.
        """
        fin = finished_at or datetime.now(timezone.utc)
        duracion = int((fin - started_at).total_seconds() * 1000) if started_at else None

        intento = AccountingAttempt(
            document_id=document_id,
            job_id=job_id,
            attempt=attempt,
            started_at=started_at,
            finished_at=fin,
            duration_ms=duracion,
            request_payload=request_payload,
            response_body=response_body,
            http_status=http_status,
            ok=ok,
            siigo_id=siigo_id,
            siigo_name=siigo_name,
            error_message=(error_message or None),
            error_code=error_code,
            error_class=error_class,
            recommended_action=recommended_action,
            triggered_by=triggered_by,
        )
        try:
            self.db.add(intento)
            self.db.commit()
            self.db.refresh(intento)
            return intento
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception(
                "RF-05: no se pudo registrar el intento %s del documento %s",
                attempt,
                document_id,
            )
            return None

    def record_field_change(
        self,
        *,
        document_id: int,
        entity: str,
        field: str,
        old_value: Any,
        new_value: Any,
        entity_id: Optional[int] = None,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Registra una corrección manual sobre la causación."""
        try:
            self.db.add(
                DocumentFieldChange(
                    document_id=document_id,
                    entity=entity,
                    entity_id=entity_id,
                    field=field,
                    old_value=None if old_value is None else str(old_value),
                    new_value=None if new_value is None else str(new_value),
                    changed_by=changed_by,
                    reason=reason,
                )
            )
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception(
                "RF-05: no se pudo registrar el cambio de %s.%s del documento %s",
                entity,
                field,
                document_id,
            )

    def attempts_for(self, document_id: int, limit: int = 50) -> list:
        return (
            self.db.query(AccountingAttempt)
            .filter(AccountingAttempt.document_id == document_id)
            .order_by(AccountingAttempt.created_at.desc())
            .limit(limit)
            .all()
        )

    def changes_for(self, document_id: int, limit: int = 100) -> list:
        return (
            self.db.query(DocumentFieldChange)
            .filter(DocumentFieldChange.document_id == document_id)
            .order_by(DocumentFieldChange.created_at.desc())
            .limit(limit)
            .all()
        )
