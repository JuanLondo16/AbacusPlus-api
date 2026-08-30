"""RF-05 / RF-06 de extremo a extremo, por HTTP.

Estas pruebas entran por la misma puerta que el frontend —una petición HTTP a la ruta que el
gateway expone— y solo sustituyen el salto final hacia SIIGO. Lo que verifican es lo que no
se puede comprobar llamando al caso de uso directamente: que la ruta existe donde el
frontend la llama, que exige autenticación, y que el cuerpo de la respuesta tiene la forma
que la interfaz consume.
"""

import pytest
from app.application.services.accounting_queue import EnqueueResult
from app.application.use_cases.account_document import (
    AccountingOutcome,
)
from app.dependencies import (
    get_account_document_use_case,
    get_accounting_queue_service,
)
from app.domain.exceptions.base import EntityNotFoundException
from app.domain.value_objects.accounting_error import RecommendedAction
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.config.auth_dependency import TokenData, get_token_data
from app.main import app
from fastapi.testclient import TestClient

RUTA_INDIVIDUAL = "/api/v1/documents/{}/accounting-entries"
RUTA_LOTE = "/api/v1/documents/accounting-entries"


class UseCaseFalso:
    """Sustituye el salto a SIIGO conservando el contrato del caso de uso."""

    def __init__(self, outcome=None, batch=None, raises=None):
        self.outcome = outcome
        self.batch = batch
        self.raises = raises
        self.forced = None

    def execute(self, document_id, force=False, *, triggered_by=None, job_id=None, attempt=1):
        if self.raises:
            raise self.raises
        self.forced = force
        self.triggered_by = triggered_by
        return self.outcome

    def execute_batch(self, document_ids):
        return self.batch


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _autenticar(roles=("operator",)):
    """Simula un usuario autenticado. Por defecto con permiso de escritura.

    El rol importa desde que los endpoints de contabilización exigen `require_write`: un
    `viewer` no puede crear facturas de compra en SIIGO.
    """
    app.dependency_overrides[get_token_data] = lambda: TokenData(
        {
            "sub": "1",
            "tenant_id": 1,
            "tenant_slug": "demo",
            "type": "access",
            "roles": list(roles),
        },
        "token-de-prueba",
    )


def _usar(use_case):
    app.dependency_overrides[get_account_document_use_case] = lambda: use_case


class ColaFalsa:
    """Sustituye la cola conservando su contrato.

    La cola solo escribe filas: no habla con SIIGO ni con la base de otro servicio, así que
    sustituirla aquí no oculta ningún riesgo real. Lo que estas pruebas verifican del lote es
    lo que solo se ve por HTTP: que responde 202 sin esperar a SIIGO, y que el cuerpo trae lo
    aceptado y lo rechazado con la forma que la interfaz consume.
    """

    def __init__(self, resultado=None, raises=None):
        self.resultado = resultado
        self.raises = raises
        self.recibidos = None
        self.enqueued_by = None

    def enqueue(self, document_ids, *, enqueued_by=None, batch_id=None):
        if self.raises:
            raise self.raises
        self.recibidos = list(document_ids)
        self.enqueued_by = enqueued_by
        return self.resultado

    def progress(self, batch_id):
        return {
            "batch_id": batch_id,
            "total": 2,
            "pending": 0,
            "running": 0,
            "successful": 1,
            "failed": 0,
            "needs_reconciliation": 1,
            "cancelled": 0,
            "finished": 2,
            "done": True,
        }


def _usar_cola(cola):
    app.dependency_overrides[get_accounting_queue_service] = lambda: cola


# ── Seguridad ──────────────────────────────────────────────────────────────────


def test_sin_token_no_se_puede_contabilizar(client):
    """La ruta está protegida: no basta con ocultar el botón en la interfaz."""
    respuesta = client.post(RUTA_INDIVIDUAL.format(1))
    assert respuesta.status_code in (401, 403)


def test_sin_token_no_se_puede_contabilizar_en_lote(client):
    respuesta = client.post(RUTA_LOTE, json={"document_ids": [1, 2]})
    assert respuesta.status_code in (401, 403)


# ── Flujo exitoso ──────────────────────────────────────────────────────────────


def test_contabilizacion_exitosa_devuelve_201_con_el_id_de_siigo(client):
    _autenticar()
    _usar(
        UseCaseFalso(
            outcome=AccountingOutcome(
                document_id=1,
                ok=True,
                status=DocumentStatus.CONTABILIZADA,
                siigo_id="63f918c2-ca65-4edc-a7db-66bcdd5159fb",
                siigo_name="FC-1-125",
            )
        )
    )

    respuesta = client.post(RUTA_INDIVIDUAL.format(1))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert cuerpo["status"] == DocumentStatus.CONTABILIZADA
    assert cuerpo["siigo_id"] == "63f918c2-ca65-4edc-a7db-66bcdd5159fb"
    assert cuerpo["siigo_name"] == "FC-1-125"


# ── RF-06: el error llega al frontend ──────────────────────────────────────────


def test_error_de_siigo_devuelve_422_con_el_motivo(client):
    """RF-06: el mensaje de SIIGO viaja hasta la interfaz para que el contador lo lea."""
    _autenticar()
    _usar(
        UseCaseFalso(
            outcome=AccountingOutcome(
                document_id=1,
                ok=False,
                status=DocumentStatus.ERROR,
                error="La cuenta 51951001 no existe en Siigo Nube",
            )
        )
    )

    respuesta = client.post(RUTA_INDIVIDUAL.format(1))

    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["error"] == "La cuenta 51951001 no existe en Siigo Nube"
    assert detalle["status"] == DocumentStatus.ERROR
    assert detalle["needs_reconciliation"] is False


def test_documento_bloqueado_avisa_que_requiere_reconciliacion(client):
    """El frontend usa esta bandera para NO ofrecer el botón de reintento."""
    _autenticar()
    _usar(
        UseCaseFalso(
            outcome=AccountingOutcome(
                document_id=1,
                ok=False,
                # El estado es Error, como cualquier otro fallo: lo que marca este caso es
                # la acción recomendada, no un estado propio.
                status=DocumentStatus.ERROR,
                error="SIIGO no respondió a tiempo",
                recommended_action=RecommendedAction.RECONCILE,
                needs_reconciliation=True,
            )
        )
    )

    respuesta = client.post(RUTA_INDIVIDUAL.format(1))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["needs_reconciliation"] is True


def test_documento_ya_contabilizado_responde_409(client):
    _autenticar()
    _usar(
        UseCaseFalso(
            outcome=AccountingOutcome(
                document_id=1,
                ok=False,
                status=DocumentStatus.CONTABILIZADA,
                siigo_id="63f9-abc",
                error="El documento ya está contabilizado en SIIGO.",
            )
        )
    )

    assert client.post(RUTA_INDIVIDUAL.format(1)).status_code == 409


def test_documento_inexistente_responde_404(client):
    _autenticar()
    _usar(UseCaseFalso(raises=EntityNotFoundException("Document", "999")))

    assert client.post(RUTA_INDIVIDUAL.format(999)).status_code == 404


# ── Lotes ──────────────────────────────────────────────────────────────────────


def test_el_lote_encola_y_responde_202_sin_esperar_a_siigo(client):
    """El lote ya no contabiliza dentro de la petición: encola y devuelve el acuse.

    Es la diferencia que hace que un envío de doscientos documentos no mantenga una conexión
    HTTP abierta durante minutos, ni pierda el rastro de lo ya enviado si el proceso muere.
    """
    _autenticar()
    cola = ColaFalsa(
        EnqueueResult(
            batch_id="lote-1",
            enqueued=[{"document_id": 1, "job_id": 10}, {"document_id": 3, "job_id": 11}],
            rejected=[{"document_id": 2, "reason": "El documento ya está contabilizado."}],
        )
    )
    _usar_cola(cola)

    respuesta = client.post(RUTA_LOTE, json={"document_ids": [1, 2, 3]})

    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    assert cuerpo["batch_id"] == "lote-1"
    assert cuerpo["total"] == 3
    assert len(cuerpo["enqueued"]) == 2
    # Un documento rechazado no invalida el lote: los demás siguen su curso, y el motivo
    # llega al usuario para que sepa qué quedó fuera.
    assert cuerpo["rejected"][0]["reason"] == "El documento ya está contabilizado."
    assert cola.recibidos == [1, 2, 3]


def test_el_progreso_del_lote_separa_los_pendientes_de_verificar(client):
    """`needs_reconciliation` va aparte de `failed` porque su tratamiento es distinto."""
    _autenticar()
    _usar_cola(ColaFalsa())

    respuesta = client.get("/api/v1/documents/accounting-batches/lote-1")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["needs_reconciliation"] == 1
    assert cuerpo["failed"] == 0
    assert cuerpo["done"] is True


def test_lote_vacio_es_rechazado(client):
    _autenticar()
    _usar_cola(ColaFalsa(EnqueueResult(batch_id="x")))

    assert client.post(RUTA_LOTE, json={"document_ids": []}).status_code == 422


def test_lote_por_encima_del_maximo_es_rechazado(client):
    """El límite se valida en el borde, antes de tocar la base o SIIGO.

    El tope lo fija `ACCOUNTING_BATCH_MAX_SIZE`; se envía deliberadamente muy por encima de
    cualquier valor razonable para que la prueba no dependa de la configuración concreta.
    """
    _autenticar()
    _usar_cola(ColaFalsa(EnqueueResult(batch_id="x")))

    respuesta = client.post(RUTA_LOTE, json={"document_ids": list(range(5000))})

    assert respuesta.status_code == 422


def test_force_llega_al_caso_de_uso(client):
    """RF-06: la interfaz debe poder pedir el reintento explícito de un documento atascado."""
    _autenticar()
    uc = UseCaseFalso(
        outcome=AccountingOutcome(
            document_id=1, ok=True, status=DocumentStatus.CONTABILIZADA, siigo_id="a"
        )
    )
    _usar(uc)

    client.post(RUTA_INDIVIDUAL.format(1) + "?force=true")
    assert uc.forced is True


def test_sin_force_el_caso_de_uso_no_lo_recibe(client):
    """El valor por defecto no puede ser forzar: sería reenviar sin verificación."""
    _autenticar()
    uc = UseCaseFalso(
        outcome=AccountingOutcome(
            document_id=1, ok=True, status=DocumentStatus.CONTABILIZADA, siigo_id="a"
        )
    )
    _usar(uc)

    client.post(RUTA_INDIVIDUAL.format(1))
    assert uc.forced is False


# ── 4. Control de acceso por rol (H-01) ────────────────────────────────────────


def test_un_viewer_no_puede_contabilizar_un_documento(client):
    """RF-05: crear una factura de compra en SIIGO es irreversible y exige permiso.

    Antes de introducir `require_write`, el rol no se comprobaba en ningún punto: un usuario
    invitado como «solo lectura» podía contabilizar exactamente igual que un administrador.
    """
    _autenticar(roles=("viewer",))
    uc = UseCaseFalso(
        outcome=AccountingOutcome(
            document_id=1, ok=True, status=DocumentStatus.CONTABILIZADA, siigo_id="a"
        )
    )
    _usar(uc)

    respuesta = client.post(RUTA_INDIVIDUAL.format(1))

    assert respuesta.status_code == 403
    assert uc.forced is None  # el caso de uso no llegó a ejecutarse


def test_un_viewer_tampoco_puede_contabilizar_por_lotes(client):
    """El lote no puede ser la puerta trasera de la acción individual."""
    _autenticar(roles=("viewer",))
    uc = UseCaseFalso(outcome=None)
    _usar(uc)

    respuesta = client.post(RUTA_LOTE, json={"document_ids": [1, 2]})

    assert respuesta.status_code == 403


def test_un_token_sin_ningun_rol_es_rechazado(client):
    """Todo usuario recibe un rol al crearse; su ausencia no es un caso legítimo."""
    _autenticar(roles=())
    _usar(UseCaseFalso(outcome=None))

    assert client.post(RUTA_INDIVIDUAL.format(1)).status_code == 403


@pytest.mark.parametrize("rol", ["tenant_admin", "operator"])
def test_los_roles_de_escritura_si_pueden_contabilizar(client, rol):
    _autenticar(roles=(rol,))
    _usar(
        UseCaseFalso(
            outcome=AccountingOutcome(
                document_id=1, ok=True, status=DocumentStatus.CONTABILIZADA, siigo_id="a"
            )
        )
    )

    assert client.post(RUTA_INDIVIDUAL.format(1)).status_code == 201
