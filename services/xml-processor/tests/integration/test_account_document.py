"""RF-05: contabilización en SIIGO.

Las pruebas se agrupan por la pregunta que responden, no por método, porque lo que hay que
demostrar aquí no es que el código corra: es que **un documento no se contabilice dos veces**
y que **nunca se marque como contabilizado sin prueba de SIIGO**.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from app.application.use_cases.account_document import AccountDocumentUseCase
from app.domain.exceptions.base import EntityNotFoundException
from app.domain.value_objects.accounting_error import ErrorClass, RecommendedAction
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.clients.siigo_client import PurchaseInvoiceResult

PARAMETROS = {
    "document_id": 7100,
    "supplier_branch_office": 0,
    "default_payment_id": 5636,
    "account_key": "default",
}


def _documento(**overrides):
    base = {
        "id": 1,
        "status": DocumentStatus.APROBADO,
        "date": date(2026, 8, 10),
        "issuer_nit": "900123456-7",
        "document_number": "990000001",
        "total": 150000.0,
        "payment_type_id": 5636,
        "cost_center_id": 1235,
        "siigo_id": None,
        "accounting_locked": False,
        "accounting_error": None,
        "accounting_error_class": None,
        "accounting_recommended_action": None,
        "accounting_attempts": 0,
        "details": [
            SimpleNamespace(
                code="51951001",
                type="Account",
                quantity=1,
                price=150000.0,
                description="Mantenimiento",
                tax_id=13156,
            )
        ],
        "taxes": [SimpleNamespace(tax_id=1136, value=5000.0)],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class RepoFalso:
    """Repositorio en memoria que reproduce la semántica del cerrojo real.

    `claim_for_accounting` devuelve None cuando el documento tiene el cerrojo puesto o su
    estado no lo permite, que es exactamente lo que hace `SELECT ... FOR UPDATE` seguido de
    la verificación. El cerrojo es una columna y no un estado: el documento en curso sigue
    viéndose como Aprobado, y uno que falló se ve como Error pase lo que pase.
    """

    def __init__(self, doc):
        self.doc = doc
        self.claims = 0
        self.marked_accounted = []
        self.failures = []

    def get_by_id(self, document_id):
        return self.doc if self.doc and self.doc.id == document_id else None

    def claim_for_accounting(self, document_id, force=False):
        self.claims += 1
        if self.doc.accounting_locked and not force:
            return None
        puede = self.doc.status == DocumentStatus.APROBADO or (
            self.doc.status == DocumentStatus.ERROR and bool(self.doc.accounting_error)
        )
        if not puede:
            return None
        self.doc.accounting_locked = True
        self.doc.accounting_attempts += 1
        return self.doc

    def mark_accounted(
        self,
        document_id,
        siigo_id,
        siigo_name=None,
        *,
        siigo_total=None,
        total_matches_dian=None,
    ):
        self.marked_accounted.append((document_id, siigo_id))
        self.doc.status = DocumentStatus.CONTABILIZADA
        self.doc.siigo_id = siigo_id
        self.doc.accounting_locked = False
        return self.doc

    def mark_accounting_failed(
        self,
        document_id,
        error,
        *,
        release,
        error_class=None,
        recommended_action=None,
        error_code=None,
    ):
        self.failures.append((document_id, error, release))
        self.doc.accounting_error = error
        self.doc.accounting_error_class = error_class
        self.doc.accounting_recommended_action = recommended_action
        self.doc.status = DocumentStatus.ERROR
        if release:
            self.doc.accounting_locked = False
        return self.doc


class ClienteFalso:
    def __init__(self, result, spy=None):
        self.result = result
        self.calls = []
        self.spy = spy

    def create_purchase_invoice(self, payload):
        self.calls.append(payload)
        if self.spy:
            self.spy(payload)
        return self.result


def _use_case(doc, result, parametros=PARAMETROS):
    repo = RepoFalso(doc)
    client = ClienteFalso(result)
    uc = AccountDocumentUseCase(repo, lambda: parametros, client)
    return uc, repo, client


# ── 1. Camino feliz ────────────────────────────────────────────────────────────


def test_documento_aprobado_se_contabiliza_y_guarda_el_id():
    doc = _documento()
    uc, repo, client = _use_case(
        doc, PurchaseInvoiceResult(ok=True, siigo_id="63f9-abc", siigo_name="FC-1-125")
    )

    out = uc.execute(1)

    assert out.ok is True
    assert out.status == DocumentStatus.CONTABILIZADA
    assert out.siigo_id == "63f9-abc"
    assert repo.marked_accounted == [(1, "63f9-abc")]


def test_el_json_enviado_sale_del_documento_real():
    doc = _documento()
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    uc.execute(1)
    enviado = client.calls[0]

    assert enviado["document_id"] == 7100  # de la plantilla, no inventado
    assert enviado["date"] == "2026-08-10"
    assert enviado["supplier_identification"] == "900123456"  # sin dígito de verificación
    assert enviado["items"][0]["code"] == "51951001"
    assert enviado["items"][0]["tax_ids"] == [13156]
    assert enviado["payment_id"] == 5636
    assert enviado["payment_value"] == 150000.0
    assert enviado["cost_center"] == 1235  # RF-07
    assert enviado["retention_ids"] == [1136]  # RF-02
    assert enviado["provider_invoice_number"] == "990000001"


# ── 2. Nunca contabilizado sin prueba ──────────────────────────────────────────


def test_respuesta_sin_id_no_marca_contabilizado_y_bloquea():
    """Un 201 sin id no es éxito: sin id no hay forma de reconciliar después."""
    doc = _documento()
    uc, repo, _ = _use_case(
        doc,
        PurchaseInvoiceResult(
            ok=False, error="SIIGO no devolvió el identificador", no_response=True
        ),
    )

    out = uc.execute(1)

    assert out.ok is False
    assert repo.marked_accounted == []
    # El estado funcional es Error, como en cualquier otro fallo. Lo que impide el reenvío
    # es el cerrojo, no un estado especial.
    assert out.status == DocumentStatus.ERROR
    assert doc.accounting_locked is True
    assert out.recommended_action == RecommendedAction.RECONCILE
    assert out.needs_reconciliation is True


@pytest.mark.parametrize(
    "resultado",
    [
        # Timeout y corte de red: la petición pudo llegar y crear la factura.
        PurchaseInvoiceResult(ok=False, error="SIIGO no respondió a tiempo", no_response=True),
        PurchaseInvoiceResult(
            ok=False, error="No fue posible comunicarse con SIIGO", no_response=True
        ),
        # Duplicado: el comprobante YA existe en SIIGO.
        PurchaseInvoiceResult(
            ok=False,
            error="El comprobante ya existe",
            status_code=409,
            siigo_codes=["duplicated_document"],
        ),
    ],
)
def test_desenlace_incierto_deja_el_documento_bloqueado(resultado):
    """El caso crítico: si no consta que SIIGO no creó nada, el cerrojo NO se abre.

    Abrirlo permitiría reenviar el documento — y como /v1/purchases no admite
    `Idempotency-Key`, eso crearía una segunda factura real en la contabilidad del cliente.
    """
    doc = _documento()
    uc, repo, _ = _use_case(doc, resultado)

    out = uc.execute(1)

    assert out.status == DocumentStatus.ERROR
    assert out.needs_reconciliation is True
    assert out.recommended_action == RecommendedAction.RECONCILE
    assert repo.failures[0][2] is False  # release=False
    assert doc.accounting_locked is True


@pytest.mark.parametrize(
    "http_status,accion",
    [
        (400, RecommendedAction.EDIT_AND_RETRY),
        (401, RecommendedAction.FIX_CONFIGURATION),
        (403, RecommendedAction.FIX_CONFIGURATION),
        (404, RecommendedAction.EDIT_AND_RETRY),
        (422, RecommendedAction.EDIT_AND_RETRY),
        (429, RecommendedAction.RETRY),
        (503, RecommendedAction.RETRY),
    ],
)
def test_error_confirmado_de_siigo_libera_el_cerrojo(http_status, accion):
    """Cuando consta que SIIGO rechazó sin crear nada, el documento vuelve a ser enviable.

    Cada código además determina QUÉ puede hacer el usuario, que es la parte que sustituye a
    los estados que no se crearon: el estado siempre es Error, la acción es la que cambia.
    """
    doc = _documento()
    uc, repo, _ = _use_case(
        doc, PurchaseInvoiceResult(ok=False, error=f"SIIGO {http_status}", status_code=http_status)
    )

    out = uc.execute(1)

    assert out.status == DocumentStatus.ERROR
    assert out.needs_reconciliation is False
    assert out.recommended_action == accion
    assert repo.failures[0][2] is True  # release=True
    assert doc.accounting_locked is False


@pytest.mark.parametrize("http_status", [500, 502, 504])
def test_los_5xx_no_liberan_el_cerrojo(http_status):
    """Regresión del defecto más grave que tenía RF-05.

    `siigo_did_not_create` devolvía True para todo el rango 400–599, así que un 500 de SIIGO
    dejaba el documento reenviable. Un 5xx es indistinguible entre «falló antes de crear» y
    «creó y falló al responder», y reenviar en el segundo caso duplica un asiento real.
    """
    doc = _documento()
    uc, repo, _ = _use_case(
        doc, PurchaseInvoiceResult(ok=False, error=f"SIIGO {http_status}", status_code=http_status)
    )

    out = uc.execute(1)

    assert out.status == DocumentStatus.ERROR
    assert out.error_class == ErrorClass.UNCERTAIN
    assert out.recommended_action == RecommendedAction.RECONCILE
    assert out.needs_reconciliation is True
    assert repo.failures[0][2] is False
    assert doc.accounting_locked is True


# ── 3. Doble contabilización ───────────────────────────────────────────────────


def test_documento_ya_contabilizado_no_se_reenvia():
    doc = _documento(status=DocumentStatus.CONTABILIZADA, siigo_id="63f9-abc")
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="otro"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []  # no se llamó a SIIGO
    assert "ya está contabilizado" in out.error


def test_documento_en_curso_no_se_reenvia():
    doc = _documento(status=DocumentStatus.APROBADO, accounting_locked=True)
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert out.needs_reconciliation is True


def test_dos_envios_simultaneos_solo_llaman_a_siigo_una_vez():
    """Simula doble clic: el segundo llega cuando el primero ya tomó el cerrojo."""
    doc = _documento()
    uc, repo, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="63f9-abc"))

    primero = uc.execute(1)
    segundo = uc.execute(1)  # el estado ya no es APROBADO

    assert primero.ok is True
    assert segundo.ok is False
    assert len(client.calls) == 1


def test_documento_no_aprobado_es_rechazado_aunque_se_llame_directo_al_backend():
    """Seguridad: el backend no confía en que el frontend haya ocultado el botón."""
    doc = _documento(status=DocumentStatus.CAUSADO)
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []


# ── 4. Validación previa ───────────────────────────────────────────────────────


def test_linea_sin_cuenta_puc_no_llega_a_siigo():
    doc = _documento(
        details=[
            SimpleNamespace(
                code=None, type="Account", quantity=1, price=100.0, description="x", tax_id=None
            )
        ]
    )
    uc, repo, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert "cuenta contable" in out.error
    assert out.status == DocumentStatus.ERROR  # RF-06: queda en Error, es corregible
    assert repo.failures[0][2] is True


def test_sin_plantilla_de_parametros_no_se_inventa_el_tipo_de_comprobante():
    doc = _documento()
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"), parametros=None)

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert "plantilla de parámetros" in out.error


def test_sin_forma_de_pago_no_se_envia():
    doc = _documento(payment_type_id=None)
    uc, _, client = _use_case(
        doc,
        PurchaseInvoiceResult(ok=True, siigo_id="x"),
        parametros={**PARAMETROS, "default_payment_id": None},
    )

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert "forma de pago" in out.error


def test_documento_inexistente():
    uc = AccountDocumentUseCase(RepoFalso(None), lambda: PARAMETROS, ClienteFalso(None))
    with pytest.raises(EntityNotFoundException):
        uc.execute(999)


# ── 5. Lotes ───────────────────────────────────────────────────────────────────


def test_lote_continua_cuando_un_documento_falla():
    """Un proveedor mal configurado no puede bloquear el cierre contable del mes."""
    docs = {
        1: _documento(id=1),
        2: _documento(
            id=2,
            details=[
                SimpleNamespace(
                    code=None, type="Account", quantity=1, price=1.0, description="x", tax_id=None
                )
            ],
        ),
        3: _documento(id=3),
    }

    class RepoMulti(RepoFalso):
        def __init__(self, docs):
            self.docs = docs
            self.failures = []
            self.marked_accounted = []

        def get_by_id(self, document_id):
            return self.docs.get(document_id)

        def claim_for_accounting(self, document_id, force=False):
            doc = self.docs.get(document_id)
            if doc is None or doc.status != DocumentStatus.APROBADO:
                return None
            if doc.accounting_locked and not force:
                return None
            doc.accounting_locked = True
            return doc

        def mark_accounted(
            self,
            document_id,
            siigo_id,
            siigo_name=None,
            *,
            siigo_total=None,
            total_matches_dian=None,
        ):
            self.marked_accounted.append(document_id)
            self.docs[document_id].status = DocumentStatus.CONTABILIZADA
            return self.docs[document_id]

        def mark_accounting_failed(
            self,
            document_id,
            error,
            *,
            release,
            error_class=None,
            recommended_action=None,
            error_code=None,
        ):
            self.failures.append(document_id)
            self.docs[document_id].accounting_error = error
            if release:
                self.docs[document_id].status = DocumentStatus.ERROR
            return self.docs[document_id]

    repo = RepoMulti(docs)
    uc = AccountDocumentUseCase(
        repo, lambda: PARAMETROS, ClienteFalso(PurchaseInvoiceResult(ok=True, siigo_id="ok"))
    )

    out = uc.execute_batch([1, 2, 3])

    assert out.total == 3
    assert out.successful == 2
    assert out.failed == 1
    assert sorted(repo.marked_accounted) == [1, 3]


# El tope del lote dejó de ser una constante del caso de uso: lo impone ahora el servicio de
# cola a partir de `ACCOUNTING_BATCH_MAX_SIZE`, porque encolar es lo que el usuario hace y
# `execute_batch` quedó como camino interno. Su prueba vive en `test_accounting_queue.py`.


# ── 6. RF-06 ↔ RF-05: el error se guarda y permite reintentar ──────────────────


def test_documento_en_error_de_contabilizacion_puede_reintentarse():
    """RF-06: «El documento con error queda en estado Error y puede reintentarse»."""
    doc = _documento(status=DocumentStatus.ERROR, accounting_error="SIIGO 422: cuenta inválida")
    uc, repo, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="63f9-ok"))

    out = uc.execute(1)

    assert out.ok is True
    assert out.status == DocumentStatus.CONTABILIZADA
    assert len(client.calls) == 1


def test_documento_en_error_de_procesamiento_no_puede_contabilizarse():
    """Un Error sin intento de contabilización nunca estuvo aprobado: no debe llegar a SIIGO.

    Es lo que separa «falló contabilizando» de «su XML no se pudo procesar». Sin esta
    distinción, abrir el reintento desde Error dejaría contabilizar documentos que el
    contador jamás aprobó.
    """
    doc = _documento(status=DocumentStatus.ERROR, accounting_error=None)
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []


def test_el_error_de_siigo_queda_asociado_al_documento():
    """RF-06: el mensaje devuelto por SIIGO se guarda para que el usuario lo revise."""
    doc = _documento()
    uc, repo, _ = _use_case(
        doc,
        PurchaseInvoiceResult(
            ok=False,
            error="La cuenta 51951001 no existe en Siigo Nube",
            status_code=400,
            siigo_codes=["invalid_reference"],
        ),
    )

    out = uc.execute(1)

    # El mensaje de SIIGO se conserva íntegro dentro del mensaje compuesto: el contador
    # necesita saber qué hacer, y el soporte qué dijo SIIGO exactamente.
    assert "La cuenta 51951001 no existe en Siigo Nube" in out.error
    assert "La cuenta 51951001 no existe en Siigo Nube" in doc.accounting_error
    # Y queda clasificado como corregible, que es lo que habilita «Editar y reintentar».
    assert out.error_class == ErrorClass.CORRECTABLE
    assert out.recommended_action == RecommendedAction.EDIT_AND_RETRY
    assert out.error_code == "invalid_reference"


# ── 7. RF-06: reintento tras fallo de comunicación (force) ─────────────────────


def test_documento_atascado_puede_reintentarse_de_forma_explicita():
    """El reintento tras un fallo de comunicación existe, pero exige una decisión explícita.

    El documento queda con el cerrojo puesto para que ningún clic accidental lo reenvíe.
    `force` lo salta, y solo debe llegar en True desde la reconciliación, que es el camino en
    el que alguien verificó contra SIIGO que la factura no existe.
    """
    doc = _documento(
        status=DocumentStatus.ERROR,
        accounting_locked=True,
        accounting_error="SIIGO no respondió",
    )
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="63f9-ok"))

    out = uc.execute(1, force=True)

    assert out.ok is True
    assert out.status == DocumentStatus.CONTABILIZADA
    assert len(client.calls) == 1


def test_documento_atascado_no_se_reenvia_sin_force():
    doc = _documento(
        status=DocumentStatus.ERROR,
        accounting_locked=True,
        accounting_error="SIIGO no respondió",
    )
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert out.needs_reconciliation is True


def test_el_lote_nunca_fuerza_un_documento_atascado():
    """Un lote no puede arrastrar un documento que exige verificación humana."""
    doc = _documento(
        status=DocumentStatus.ERROR, accounting_locked=True, accounting_error="timeout"
    )
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute_batch([1])

    assert out.successful == 0
    assert client.calls == []


# ── 8. Requisitos reales del comprobante configurado en SIIGO ─────────────────


def test_sin_centro_de_costo_el_documento_igual_se_envia():
    """RF-07: el centro de costo es opcional a nivel de documento.

    Quien decide si el comprobante lo exige es la configuración de la empresa en SIIGO, y
    esa regla la aplica el siigo-service leyendo `cost_center_mandatory`. Duplicarla aquí
    crearía dos verdades que pueden discrepar.
    """
    doc = _documento(cost_center_id=None)
    uc, _, client = _use_case(
        doc,
        PurchaseInvoiceResult(ok=True, siigo_id="ok"),
        parametros={**PARAMETROS, "cost_center": None},
    )

    out = uc.execute(1)

    assert out.ok is True
    assert "cost_center" not in client.calls[0]  # opcional ausente: se omite, no se manda null


def test_se_envia_fecha_de_vencimiento_del_pago():
    """SIIGO exige `due_date` si el medio de pago maneja vencimiento.

    Los típicos de compra a crédito lo manejan, y el documento DIAN no trae vencimiento, así
    que se usa la fecha del comprobante en vez de omitirlo y que SIIGO lo rechace.
    """
    doc = _documento()
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    uc.execute(1)

    assert client.calls[0]["payment_due_date"] == "2026-08-10"


def test_el_centro_de_costo_del_documento_prevalece_sobre_la_plantilla():
    doc = _documento(cost_center_id=735)
    uc, _, client = _use_case(
        doc,
        PurchaseInvoiceResult(ok=True, siigo_id="x"),
        parametros={**PARAMETROS, "cost_center": 999},
    )

    uc.execute(1)

    assert client.calls[0]["cost_center"] == 735


# ── 8. Fallos de configuración, que no son fallos del documento ────────────────


def test_la_plantilla_ausente_no_pide_editar_el_documento():
    """Un problema de configuración no se arregla editando el documento.

    Es el caso de «no hay una plantilla de parámetros de factura de compra configurada». No
    hay ningún dato del documento que cambiar: la plantilla es única para toda la empresa y
    se configura en Integraciones. Clasificarlo como corregible ofrecía el botón «Editar
    documento», que mandaba al contador a buscar durante un rato algo que no existía.

    Reintentar, en cambio, SÍ debe estar disponible: SIIGO no llegó a llamarse, así que en
    cuanto la plantilla esté puesta el reenvío es seguro.
    """
    from app.domain.value_objects.accounting_error import can_edit, can_retry

    doc = _documento()
    uc, repo, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))
    uc.parameters_provider = lambda: None

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []  # no se gastó una llamada a SIIGO
    assert out.status == DocumentStatus.ERROR
    assert out.error_class == ErrorClass.CONFIG
    assert can_edit(out.recommended_action) is False
    assert can_retry(out.recommended_action) is True
    # El cerrojo queda abierto: consta que no se creó nada.
    assert doc.accounting_locked is False
    assert "Integraciones" in out.error


def test_un_dato_que_falta_en_el_documento_si_pide_editarlo():
    """El contraste con el caso anterior: aquí sí hay algo que corregir en el documento."""
    from app.domain.value_objects.accounting_error import can_edit

    doc = _documento(issuer_nit=None)
    uc, _, client = _use_case(doc, PurchaseInvoiceResult(ok=True, siigo_id="x"))

    out = uc.execute(1)

    assert out.ok is False
    assert client.calls == []
    assert out.error_class == ErrorClass.CORRECTABLE
    assert can_edit(out.recommended_action) is True
