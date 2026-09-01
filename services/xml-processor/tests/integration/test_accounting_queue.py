"""RF-05: la cola de contabilización.

Lo que estas pruebas demuestran no es que la cola funcione, sino que **no puede duplicar una
contabilización**. Cada barrera del diseño tiene aquí su prueba:

1. un documento con el cerrojo puesto no se encola;
2. un documento ya encolado no se encola dos veces;
3. un fallo de desenlace desconocido no se reintenta solo;
4. un fallo temporal sí se reintenta, y con espera.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.application.services.accounting_queue import AccountingQueueService
from app.application.services.retry_manager import RetryManager
from app.domain.value_objects.accounting_error import ErrorClass
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.config.accounting_settings import AccountingSettings


def _documento(**overrides):
    base = {
        "id": 1,
        "status": DocumentStatus.APROBADO,
        "accounting_locked": False,
        "accounting_error": None,
        "siigo_id": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class RepoDocsFalso:
    def __init__(self, *docs):
        self.docs = {d.id: d for d in docs}

    def get_by_id(self, document_id):
        return self.docs.get(document_id)


class RepoJobsFalso:
    """Reproduce la semántica del índice único parcial sobre los trabajos activos."""

    def __init__(self):
        self.jobs = {}
        self.siguiente_id = 1

    def enqueue(self, document_id, *, max_attempts, batch_id=None, enqueued_by=None):
        # Es lo que hace `uq_accounting_jobs_active` en PostgreSQL: rechaza el alta si el
        # documento ya tiene un trabajo vivo. En la base es un índice y no una consulta
        # previa, porque una consulta previa tiene una carrera y un índice no.
        if any(
            j.document_id == document_id and j.state in ("PENDING", "RUNNING")
            for j in self.jobs.values()
        ):
            return None
        job = SimpleNamespace(
            id=self.siguiente_id,
            document_id=document_id,
            state="PENDING",
            batch_id=batch_id,
            max_attempts=max_attempts,
            enqueued_by=enqueued_by,
        )
        self.jobs[job.id] = job
        self.siguiente_id += 1
        return job

    def batch_progress(self, batch_id):
        del batch_id
        return {}

    def cancel(self, job_id):
        del job_id
        return True


def _cola(*docs, settings=None):
    jobs = RepoJobsFalso()
    servicio = AccountingQueueService(
        document_repo=RepoDocsFalso(*docs),
        job_repo=jobs,
        settings=settings or AccountingSettings(),
    )
    return servicio, jobs


# ── Qué entra en la cola y qué no ──────────────────────────────────────────────


def test_un_documento_aprobado_se_encola():
    cola, jobs = _cola(_documento())

    resultado = cola.enqueue([1], enqueued_by="ana@ikbo.co")

    assert len(resultado.enqueued) == 1
    assert resultado.rejected == []
    assert jobs.jobs[1].enqueued_by == "ana@ikbo.co"


def test_un_documento_en_error_de_contabilizacion_puede_reencolarse():
    """Es el reintento: el documento sigue en Error y vuelve a la cola sin más trámite."""
    doc = _documento(status=DocumentStatus.ERROR, accounting_error="Cuenta 510505 inválida")
    cola, _ = _cola(doc)

    resultado = cola.enqueue([1])

    assert len(resultado.enqueued) == 1


def test_un_documento_con_el_cerrojo_puesto_no_se_encola():
    """La barrera que importa: su desenlace no consta, así que reenviarlo podría duplicar.

    El documento se ve en Error igual que cualquier otro fallo —los cinco estados no cambian—
    pero el cerrojo impide que ningún camino de la aplicación lo mande otra vez a SIIGO.
    """
    doc = _documento(
        status=DocumentStatus.ERROR,
        accounting_locked=True,
        accounting_error="SIIGO no respondió a tiempo",
    )
    cola, jobs = _cola(doc)

    resultado = cola.enqueue([1])

    assert resultado.enqueued == []
    assert jobs.jobs == {}
    assert "Verifique en SIIGO" in resultado.rejected[0]["reason"]


def test_un_documento_ya_contabilizado_no_se_encola():
    cola, _ = _cola(_documento(status=DocumentStatus.CONTABILIZADA, siigo_id="abc"))

    resultado = cola.enqueue([1])

    assert resultado.enqueued == []
    assert "ya está contabilizado" in resultado.rejected[0]["reason"]


def test_el_doble_clic_no_crea_dos_trabajos():
    """Segunda barrera, independiente del cerrojo: el índice único de trabajos activos."""
    cola, jobs = _cola(_documento())

    cola.enqueue([1])
    segundo = cola.enqueue([1])

    assert len(jobs.jobs) == 1
    assert segundo.enqueued == []
    assert "ya está en la cola" in segundo.rejected[0]["reason"]


def test_un_documento_rechazado_no_impide_que_los_demas_entren():
    cola, _ = _cola(
        _documento(id=1),
        _documento(id=2, status=DocumentStatus.CONTABILIZADA),
        _documento(id=3),
    )

    resultado = cola.enqueue([1, 2, 3])

    assert [e["document_id"] for e in resultado.enqueued] == [1, 3]
    assert [r["document_id"] for r in resultado.rejected] == [2]
    assert resultado.total == 3


def test_el_lote_se_acota_por_configuracion():
    cola, _ = _cola(_documento(), settings=AccountingSettings(batch_max_size=2))

    with pytest.raises(ValueError, match="supera el máximo"):
        cola.enqueue([1, 2, 3])


# ── Política de reintentos ─────────────────────────────────────────────────────


def _manager(**overrides):
    return RetryManager(AccountingSettings(**overrides))


@pytest.mark.parametrize("clase", [ErrorClass.UNCERTAIN, ErrorClass.DUPLICATE])
def test_un_desenlace_desconocido_nunca_se_reintenta_solo(clase):
    """La regla que no se negocia, independientemente de los intentos que queden.

    Si no consta que SIIGO dejó de crear la factura, reintentar es apostar contra la
    contabilidad del cliente. Esos trabajos salen de la cola hacia verificación humana.
    """
    decision = _manager().decide(error_class=clase, attempt=1, max_attempts=5)

    assert decision.should_retry is False
    assert decision.needs_reconciliation is True


@pytest.mark.parametrize("clase", [ErrorClass.TRANSIENT, ErrorClass.RATE_LIMIT])
def test_un_fallo_temporal_se_reintenta_con_espera(clase):
    ahora = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

    decision = _manager().decide(error_class=clase, attempt=1, max_attempts=5, now=ahora)

    assert decision.should_retry is True
    assert decision.backoff_seconds > 0
    assert decision.next_attempt_at > ahora


def test_el_backoff_crece_y_tiene_techo():
    """Exponencial porque SIIGO lo recomienda explícitamente ante `requests_limit`.

    Reintentar a ritmo fijo contra un límite por minuto reproduce el 429 indefinidamente y,
    sostenido, alimenta la proporción de errores de la cuenta.
    """
    manager = _manager(backoff_base_seconds=2.0, backoff_max_seconds=10.0)

    esperas = [
        manager.decide(error_class=ErrorClass.TRANSIENT, attempt=i, max_attempts=99).backoff_seconds
        for i in (1, 2, 3, 10)
    ]

    assert esperas[0] < esperas[1] < esperas[2]
    assert esperas[3] == 10.0  # el techo se respeta


def test_un_error_corregible_no_se_reintenta_solo():
    """Repetir la misma petición con los mismos datos fallaría igual y gastaría cupo."""
    decision = _manager().decide(error_class=ErrorClass.CORRECTABLE, attempt=1, max_attempts=5)

    assert decision.should_retry is False
    assert decision.needs_reconciliation is False


def test_los_intentos_se_agotan():
    decision = _manager().decide(error_class=ErrorClass.TRANSIENT, attempt=5, max_attempts=5)

    assert decision.should_retry is False
    assert "agotaron" in decision.reason


def test_el_maximo_lo_fija_el_trabajo_y_no_la_configuracion_actual():
    """Subir el máximo global no revive trabajos ya dados por agotados con la regla vieja."""
    decision = _manager(max_attempts=10).decide(
        error_class=ErrorClass.TRANSIENT, attempt=3, max_attempts=3
    )

    assert decision.should_retry is False


# ── Arranque en frío: la cola no puede depender de que alguien entre ──────────
#
# `known_tenants()` solo conoce a los clientes que ya pidieron algo EN ESTE PROCESO. Tras un
# reinicio está vacía, así que un lote encolado antes del despliegue quedaba esperando a que
# alguien de ese cliente abriera la aplicación. Un envío al cierre del día y un despliegue
# esa noche dejaban los documentos sin contabilizar hasta la mañana siguiente, con el
# contador convencido de que ya iban camino de SIIGO.


def test_tras_un_reinicio_se_revisan_los_clientes_aprovisionados(monkeypatch):
    """Sin nadie conectado, la cola sigue encontrando a quién servir."""
    from app.infrastructure.queue import accounting_supervisor as sup

    monkeypatch.setattr(sup, "known_tenants", lambda: [])
    monkeypatch.setattr(sup, "all_tenant_slugs", lambda: ["ikbo", "otro"])
    monkeypatch.setattr(sup, "_cache_clientes", ((), 0.0))

    assert sup._clientes_a_revisar() == ["ikbo", "otro"]


def test_el_cliente_conectado_va_primero_y_no_se_duplica(monkeypatch):
    """Quien acaba de usar la aplicación es quien más probablemente tiene trabajo."""
    from app.infrastructure.queue import accounting_supervisor as sup

    monkeypatch.setattr(sup, "known_tenants", lambda: ["ikbo"])
    monkeypatch.setattr(sup, "all_tenant_slugs", lambda: ["otro", "ikbo"])
    monkeypatch.setattr(sup, "_cache_clientes", ((), 0.0))

    assert sup._clientes_a_revisar() == ["ikbo", "otro"]


def test_si_el_catalogo_falla_se_sigue_con_los_conocidos(monkeypatch):
    """Degradar es aceptable; parar la cola entera por un fallo de catálogo, no."""
    from app.infrastructure.queue import accounting_supervisor as sup

    monkeypatch.setattr(sup, "known_tenants", lambda: ["ikbo"])
    monkeypatch.setattr(sup, "all_tenant_slugs", lambda: [])
    monkeypatch.setattr(sup, "_cache_clientes", ((), 0.0))

    assert sup._clientes_a_revisar() == ["ikbo"]


def test_el_catalogo_no_se_consulta_en_cada_ciclo(monkeypatch):
    """El supervisor despierta cada pocos segundos; el catálogo cambia cada mucho.

    Sin la caché serían doce consultas por minuto a `pg_database`, para siempre, por un dato
    que solo cambia al aprovisionar un cliente.
    """
    from app.infrastructure.queue import accounting_supervisor as sup

    llamadas = []
    monkeypatch.setattr(sup, "known_tenants", lambda: [])
    monkeypatch.setattr(sup, "all_tenant_slugs", lambda: llamadas.append(1) or ["ikbo"])
    monkeypatch.setattr(sup, "_cache_clientes", ((), 0.0))

    sup._clientes_a_revisar()
    sup._clientes_a_revisar()
    sup._clientes_a_revisar()

    assert len(llamadas) == 1  # las dos siguientes salieron de la caché


# ── El cliente hacia siigo-service queda utilizable al construirse ────────────
#
# Una asignación de `self._timeout` quedó dentro de `_url()`, después de su `return`: código
# inalcanzable. El atributo nunca se creaba, y `create_purchase_invoice` moría con
# AttributeError al evaluar sus argumentos. Las demás llamadas del cliente usan timeouts
# literales, así que la avería solo aparecía en el envío real — el único camino que ninguna
# prueba ejercitaba de extremo a extremo.


def test_el_cliente_de_siigo_tiene_timeout_en_los_dos_modos():
    from app.infrastructure.clients.siigo_client import SiigoServiceClient

    usuario = SiigoServiceClient("http://siigo-service:8006", bearer_token="tok")
    worker = SiigoServiceClient("http://siigo-service:8006", tenant_slug="ikbo")

    assert usuario._timeout > 0
    assert worker._timeout > 0


def test_el_timeout_explicito_manda_sobre_la_configuracion():
    from app.infrastructure.clients.siigo_client import SiigoServiceClient

    assert SiigoServiceClient("http://x", timeout=7.5)._timeout == 7.5


def test_cada_modo_usa_su_ruta():
    """El worker va por la ruta interna; el usuario, por la pública del gateway."""
    from app.infrastructure.clients.siigo_client import SiigoServiceClient

    usuario = SiigoServiceClient("http://s", bearer_token="tok")
    worker = SiigoServiceClient("http://s", tenant_slug="ikbo")

    assert usuario._url("purchase-invoices") == "http://s/api/v1/siigo/purchase-invoices"
    assert worker._url("purchase-invoices") == "http://s/internal/siigo/purchase-invoices"


# ── Un fallo inesperado no puede tumbar la cola ni dejar el documento colgado ──


class _CasoDeUsoQueRevienta:
    def execute(self, *a, **kw):
        raise AttributeError("simula un error de programación en el envío")


def test_un_fallo_inesperado_cierra_el_trabajo_en_vez_de_escapar():
    """Sin contención, la excepción mataba el drenaje del cliente entero.

    El trabajo quedaba en RUNNING y el documento bloqueado hasta el rescate de huérfanos,
    quince minutos después, sin que nada lo indicara en la interfaz.
    """
    from app.domain.value_objects.accounting_error import ErrorClass, RecommendedAction
    from app.infrastructure.queue.accounting_worker import AccountingWorkerPool

    registrado = {}

    class JobRepoFalso:
        def claim_next(self, worker_id, *, stale_after_seconds):
            return SimpleNamespace(
                id=1,
                document_id=23,
                attempt=0,
                max_attempts=5,
                enqueued_by="u",
                next_attempt_at=None,
                created_at=datetime.now(timezone.utc),
            )

        def mark_failed(self, job_id, **kw):
            registrado.update(kw)

    pool = AccountingWorkerPool(
        session_factory=lambda: SimpleNamespace(close=lambda: None),
        job_repo_factory=lambda _s: JobRepoFalso(),
        use_case_factory=lambda _s: _CasoDeUsoQueRevienta(),
    )

    # No se propaga: el worker devuelve True y la cola puede seguir con los demás.
    assert pool._procesar_uno("test") is True
    # Y se cierra como INCIERTO: no se sabe si SIIGO recibió la petición.
    assert registrado["error_class"] == ErrorClass.UNCERTAIN
    assert registrado["recommended_action"] == RecommendedAction.RECONCILE
    assert registrado["needs_reconciliation"] is True
