"""RF-06: reconciliación de un documento atascado en «Contabilizando».

Estas pruebas cubren la operación de mayor riesgo contable de todo el sistema. Un documento
llega a «Contabilizando» cuando no consta si SIIGO creó la factura, y desde ahí solo caben
dos salidas: cerrarlo con el identificador que ya existe, o liberarlo para reenviarlo. Elegir
mal en cualquiera de los dos sentidos tiene consecuencias reales —un asiento duplicado en la
contabilidad del cliente, o una factura que existe en SIIGO y el sistema da por no
contabilizada—, así que lo que se verifica aquí no es que el código corra, sino que nunca
tome esa decisión por su cuenta cuando le falta información.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from app.application.use_cases.reconcile_document import ReconcileDocumentUseCase
from app.domain.exceptions.base import EntityNotFoundException
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.clients.siigo_client import PurchaseInvoiceLookup


class RepoFalso:
    def __init__(self, doc):
        self.doc = doc
        self.accounted = []
        self.failures = []

    def get_by_id(self, document_id):
        return self.doc

    def mark_accounted(
        self, document_id, siigo_id, siigo_name=None, *,
        siigo_total=None, total_matches_dian=None,
    ):
        self.accounted.append((document_id, siigo_id, siigo_name))
        self.doc.status = DocumentStatus.CONTABILIZADA
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
        self.doc.status = DocumentStatus.ERROR
        if release:
            self.doc.accounting_locked = False
        return self.doc

    def release_accounting_lock(
        self, document_id, *, reason, error_class=None, recommended_action=None
    ):
        """Única transición que abre el cerrojo, y la hace una persona tras verificar."""
        self.failures.append((document_id, reason, True))
        self.doc.accounting_error = reason
        self.doc.accounting_error_class = error_class
        self.doc.accounting_recommended_action = recommended_action
        self.doc.accounting_locked = False
        self.doc.status = DocumentStatus.ERROR
        return self.doc


class ClienteFalso:
    def __init__(self, lookup):
        self.lookup = lookup
        self.llamadas = []

    def find_purchase_invoice(self, provider_invoice_number, document_date=None):
        self.llamadas.append((provider_invoice_number, document_date))
        return self.lookup


def _documento(status=DocumentStatus.ERROR, numero="FE1234", accounting_locked=True):
    return SimpleNamespace(
        id=1,
        status=status,
        document_number=numero,
        date=date(2026, 8, 11),
        siigo_id=None,
        # El cerrojo sustituyó al antiguo estado «Contabilizando»: es lo que marca a un
        # documento cuyo envío quedó sin desenlace conocido, y lo único que la reconciliación
        # puede abrir.
        accounting_locked=accounting_locked,
        accounting_error=None,
        accounting_error_class=None,
        accounting_recommended_action=None,
    )


def _uc(doc, lookup=None):
    repo = RepoFalso(doc)
    cliente = ClienteFalso(lookup or PurchaseInvoiceLookup(consulted=True, matches=[]))
    return ReconcileDocumentUseCase(document_repo=repo, siigo_client=cliente), repo, cliente


# ── Consulta: no puede cambiar nada ────────────────────────────────────────────


def test_la_consulta_no_modifica_el_documento():
    """El diseño exige confirmación humana: consultar y resolver son pasos distintos."""
    doc = _documento()
    uc, repo, _ = _uc(doc, PurchaseInvoiceLookup(consulted=True, matches=[{"siigo_id": "abc"}]))

    uc.lookup(1)

    assert repo.accounted == []
    assert repo.failures == []
    assert doc.accounting_locked is True


def test_si_siigo_tiene_la_factura_se_propone_cerrar():
    doc = _documento()
    uc, _, _ = _uc(
        doc,
        PurchaseInvoiceLookup(
            consulted=True, matches=[{"siigo_id": "abc-123", "siigo_name": "FC-1-125"}]
        ),
    )

    vista = uc.lookup(1)

    assert vista.suggested_action == "close"
    assert vista.matches[0]["siigo_id"] == "abc-123"


def test_si_siigo_no_tiene_nada_se_propone_liberar():
    uc, _, _ = _uc(_documento(), PurchaseInvoiceLookup(consulted=True, matches=[]))

    vista = uc.lookup(1)

    assert vista.suggested_action == "release"
    assert vista.consulted is True


def test_si_no_se_pudo_consultar_no_se_propone_nada():
    """«No se sabe» nunca puede presentarse como «no existe»: eso invitaría a duplicar."""
    uc, _, _ = _uc(
        _documento(), PurchaseInvoiceLookup(consulted=False, error="SIIGO no respondió")
    )

    vista = uc.lookup(1)

    assert vista.suggested_action == "none"
    assert vista.consulted is False
    assert "no lo reenvíe" in vista.message.lower() or "no reenvíe" in vista.message.lower()


def test_un_documento_sin_numero_no_se_busca_en_siigo():
    """Sin número no hay forma de identificar la factura; buscar daría un falso negativo."""
    uc, _, cliente = _uc(_documento(numero=""))

    vista = uc.lookup(1)

    assert cliente.llamadas == []
    assert vista.suggested_action == "none"


def test_un_documento_que_no_esta_bloqueado_no_tiene_nada_que_reconciliar():
    # Lo que decide si hay algo que reconciliar es el CERROJO, no el estado: un documento en
    # Error sin cerrojo es un fallo normal y corregible, no un desenlace desconocido.
    uc, _, cliente = _uc(
        _documento(status=DocumentStatus.CONTABILIZADA, accounting_locked=False)
    )

    vista = uc.lookup(1)

    assert cliente.llamadas == []
    assert vista.suggested_action == "none"


def test_la_consulta_acota_por_la_fecha_del_documento():
    uc, _, cliente = _uc(_documento())

    uc.lookup(1)

    assert cliente.llamadas == [("FE1234", "2026-08-11")]


# ── Resolución: cerrar ─────────────────────────────────────────────────────────


def test_cerrar_con_el_id_de_siigo_no_vuelve_a_llamar_a_siigo():
    """La factura ya existe; volver a enviarla es exactamente lo que se quiere evitar."""
    doc = _documento()
    uc, repo, cliente = _uc(doc)

    resultado = uc.resolve(1, "abc-123", "FC-1-125")

    assert cliente.llamadas == []  # no se llamó a SIIGO
    assert repo.accounted == [(1, "abc-123", "FC-1-125")]
    assert resultado.status == DocumentStatus.CONTABILIZADA
    assert resultado.siigo_id == "abc-123"


# ── Resolución: liberar ────────────────────────────────────────────────────────


def test_liberar_deja_el_documento_en_error_para_poder_reenviarlo():
    doc = _documento()
    uc, repo, _ = _uc(doc)

    resultado = uc.resolve(1, None)

    assert resultado.status == DocumentStatus.ERROR
    assert repo.failures[0][2] is True  # release=True
    assert repo.accounted == []


# ── Guardas de estado ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "estado",
    [DocumentStatus.APROBADO, DocumentStatus.CONTABILIZADA, DocumentStatus.ERROR],
)
def test_solo_se_reconcilia_lo_que_esta_bloqueado(estado):
    """Reconciliar un documento ya resuelto solo puede deshacer trabajo correcto.

    La guarda es el cerrojo y no el estado. Un documento en Error sin cerrojo ya se sabe que
    SIIGO no lo creó —por eso se liberó—, y cerrarlo con un `siigo_id` inventado le atribuiría
    una factura que no le corresponde.
    """
    uc, repo, _ = _uc(_documento(status=estado, accounting_locked=False))

    with pytest.raises(ValueError):
        uc.resolve(1, "abc-123")

    assert repo.accounted == []
    assert repo.failures == []


def test_un_documento_inexistente_se_reporta_como_tal():
    uc = ReconcileDocumentUseCase(
        document_repo=SimpleNamespace(get_by_id=lambda _: None), siigo_client=None
    )

    with pytest.raises(EntityNotFoundException):
        uc.lookup(999)
