"""RF-05: los workers que vacían la cola de contabilización.

Un worker hace un bucle muy corto: toma un trabajo, pide permiso al limitador de tasa,
ejecuta **un** intento y aplica lo que el gestor de reintentos decida. No sabe nada de SIIGO
—de eso se ocupa el caso de uso— ni de qué significa un error —de eso, el clasificador—.

Esa estrechez es el punto. Cambiar la política de reintentos, la clasificación de errores o
la estrategia de concurrencia no debería obligar a tocar el código que mueve la cola, y
aquí no lo obliga: la concurrencia es un número de configuración, la política vive en
`RetryManager` y la clasificación en `SiigoErrorClassifier`.

Una sesión de base de datos por worker
---------------------------------------
Cada worker abre la suya. Compartir una sesión entre hilos no es seguro en SQLAlchemy, y
además el `SELECT ... FOR UPDATE SKIP LOCKED` con el que se reparten los trabajos necesita
transacciones independientes para funcionar: con una sesión común, los workers se
serializarían y la concurrencia configurada sería decorativa.
"""

import logging
import threading
import uuid
from typing import Callable, Optional

from app.application.services.retry_manager import RetryManager
from app.domain.value_objects.accounting_error import ErrorClass, RecommendedAction
from app.infrastructure.config.accounting_settings import (
    AccountingSettings,
    get_accounting_settings,
)
from app.infrastructure.queue.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class AccountingWorkerPool:
    """Conjunto de workers que consumen la cola de contabilización de un cliente.

    `session_factory` y `use_case_factory` se inyectan en lugar de construirse aquí para que
    el pool no dependa ni del sistema multi-cliente ni de cómo se arma el caso de uso. Es lo
    que permite probarlo entero sin base de datos ni SIIGO.
    """

    def __init__(
        self,
        *,
        session_factory: Callable,
        job_repo_factory: Callable,
        use_case_factory: Callable,
        settings: Optional[AccountingSettings] = None,
        rate_limiter: Optional[TokenBucketRateLimiter] = None,
    ):
        self.settings = settings or get_accounting_settings()
        self.session_factory = session_factory
        self.job_repo_factory = job_repo_factory
        self.use_case_factory = use_case_factory
        self.retry_manager = RetryManager(self.settings)
        # El limitador se comparte entre todos los workers: el cupo de peticiones por minuto
        # es de la empresa en SIIGO, no de cada hilo. Uno por worker multiplicaría el techo
        # real por el número de workers, que es exactamente el error que hay que no cometer.
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(
            self.settings.rate_limit_per_minute
        )
        self._stop = threading.Event()
        self._threads: list = []

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        for indice in range(self.settings.max_concurrency):
            worker_id = f"worker-{indice}-{uuid.uuid4().hex[:8]}"
            hilo = threading.Thread(
                target=self._run, args=(worker_id,), name=worker_id, daemon=True
            )
            hilo.start()
            self._threads.append(hilo)
        logger.info(
            "RF-05: %s worker(s) de contabilización en marcha (%s peticiones/min)",
            self.settings.max_concurrency,
            self.settings.rate_limit_per_minute,
        )

    def stop(self, timeout: float = 30.0) -> None:
        """Pide el alto y espera a que los workers terminen lo que tengan entre manos.

        Se espera a propósito en lugar de matarlos: un worker cortado en mitad de una llamada
        a SIIGO deja un trabajo cuyo desenlace nadie conoce, que es justo el estado caro de
        resolver. El margen debe permitir que termine una llamada en curso.
        """
        self._stop.set()
        for hilo in self._threads:
            hilo.join(timeout=timeout)
        self._threads = []

    # ── Bucle ──────────────────────────────────────────────────────────────────

    def _run(self, worker_id: str) -> None:
        while not self._stop.is_set():
            try:
                trabajado = self._procesar_uno(worker_id)
            except Exception:  # noqa: BLE001
                # Un fallo inesperado no puede matar al worker: dejaría la cola parada sin
                # que nada lo indique. Se registra y se sigue tras una pausa.
                logger.exception("RF-05: fallo inesperado en el worker %s", worker_id)
                trabajado = False

            if not trabajado:
                # Sin trabajo pendiente. Se duerme el intervalo de sondeo en lugar de girar
                # en vacío: un bucle sin espera consumiría una CPU entera por worker.
                self._stop.wait(self.settings.poll_interval_seconds)

    def _procesar_uno(self, worker_id: str) -> bool:
        """Procesa un trabajo. Devuelve False si no había ninguno disponible."""
        session = self.session_factory()
        try:
            job_repo = self.job_repo_factory(session)
            job = job_repo.claim_next(
                worker_id, stale_after_seconds=self.settings.stale_job_seconds
            )
            if job is None:
                return False

            intento = (job.attempt or 0) + 1
            logger.info(
                "RF-05: %s contabiliza el documento %s (intento %s de %s)",
                worker_id,
                job.document_id,
                intento,
                job.max_attempts,
            )

            # El permiso se pide DESPUÉS de tomar el trabajo y ANTES de llamar a SIIGO. Al
            # revés —esperar el permiso y luego tomar el trabajo— haría que los workers
            # gastaran permisos que quizá no llegan a usar, y el cupo se agotaría contra
            # peticiones que nunca salieron.
            self.rate_limiter.acquire()

            if self._stop.is_set():
                # Se pidió el alto mientras esperábamos turno. Se devuelve el trabajo a la
                # cola sin enviarlo: dejarlo salir ahora sería arriesgar una petición cuya
                # respuesta este proceso ya no va a leer.
                job_repo.reschedule(
                    job.id,
                    next_attempt_at=job.next_attempt_at or job.created_at,
                    attempt=job.attempt or 0,
                    error="El servicio se detuvo antes de enviar el documento.",
                    error_class=None,
                    recommended_action=None,
                )
                return False

            use_case = self.use_case_factory(session)
            try:
                outcome = use_case.execute(
                    job.document_id,
                    force=False,
                    triggered_by=job.enqueued_by or "worker",
                    job_id=job.id,
                    attempt=intento,
                )
            except Exception as exc:  # noqa: BLE001
                # Un fallo que el caso de uso no previó —un error de programación, una
                # dependencia caída— no puede escapar de aquí. Si escapa, se lleva por delante
                # el drenaje del cliente entero y deja este trabajo en RUNNING con el documento
                # bloqueado hasta que el rescate de huérfanos lo recoja, quince minutos después.
                #
                # Se cierra como INCIERTO, no como fallo corregible: desde fuera no se puede
                # saber en qué punto se interrumpió, y sin idempotencia en /v1/purchases la
                # única postura segura ante «no sé» es exigir verificación en SIIGO antes de
                # volver a enviar. Presumir que no se creó nada es exactamente la presunción
                # que fabrica duplicados.
                logger.exception(
                    "RF-05: fallo inesperado al contabilizar el documento %s", job.document_id
                )
                job_repo.mark_failed(
                    job.id,
                    error=f"Fallo inesperado durante el envío: {exc}",
                    error_class=ErrorClass.UNCERTAIN,
                    recommended_action=RecommendedAction.RECONCILE,
                    needs_reconciliation=True,
                    attempt=intento,
                )
                return True

            self._aplicar_desenlace(job_repo, job, intento, outcome)
            return True
        finally:
            session.close()

    def _aplicar_desenlace(self, job_repo, job, intento: int, outcome) -> None:
        """Traduce el resultado del intento al estado del trabajo en la cola."""
        if outcome.ok:
            job_repo.mark_succeeded(
                job.id, siigo_id=outcome.siigo_id, siigo_name=outcome.siigo_name
            )
            return

        decision = self.retry_manager.decide(
            error_class=outcome.error_class or ErrorClass.UNKNOWN,
            attempt=intento,
            max_attempts=job.max_attempts,
        )

        if decision.should_retry and decision.next_attempt_at is not None:
            logger.info("RF-05: documento %s reprogramado — %s", job.document_id, decision.reason)
            job_repo.reschedule(
                job.id,
                next_attempt_at=decision.next_attempt_at,
                attempt=intento,
                error=outcome.error or "",
                error_class=outcome.error_class,
                recommended_action=outcome.recommended_action,
                error_code=outcome.error_code,
            )
            return

        if decision.needs_reconciliation or outcome.needs_reconciliation:
            logger.warning(
                "RF-05: documento %s queda a la espera de verificación en SIIGO — %s",
                job.document_id,
                decision.reason or outcome.error,
            )

        job_repo.mark_failed(
            job.id,
            error=outcome.error or decision.reason,
            error_class=outcome.error_class,
            recommended_action=outcome.recommended_action,
            error_code=outcome.error_code,
            needs_reconciliation=decision.needs_reconciliation or outcome.needs_reconciliation,
            attempt=intento,
        )

    # ── Modo síncrono, para pruebas y para ejecuciones puntuales ───────────────

    def drain(self, max_jobs: int = 100, worker_id: str = "drain") -> int:
        """Procesa la cola hasta vaciarla, en el hilo actual. Devuelve cuántos procesó.

        Existe para poder probar el comportamiento completo de la cola de forma determinista,
        sin hilos ni esperas. Un test que arranca hilos y duerme para ver si algo pasó es un
        test que falla de vez en cuando por motivos que no tienen que ver con el código.
        """
        procesados = 0
        while procesados < max_jobs:
            if not self._procesar_uno(worker_id):
                break
            procesados += 1
        return procesados
