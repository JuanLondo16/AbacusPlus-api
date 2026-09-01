"""RF-08: el RAG solo aprende de causaciones efectivamente contabilizadas en SIIGO.

Cada prueba corresponde a uno de los criterios de aceptación del requisito. Lo que se
demuestra no es que el código publique conocimiento, sino **cuándo se niega a publicarlo**:
un documento aprobado pero no contabilizado, o uno cuyo envío a SIIGO falló, no pueden dejar
ningún rastro en el RAG, porque a partir de ahí ese rastro se propaga a todas las
sugerencias posteriores.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from app.application.services.accounting_knowledge import AccountingKnowledgePublisher
from app.application.use_cases.account_document import AccountDocumentUseCase
from app.domain.services.rag_content import build_accounted_knowledge_content
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
        "document_number": "990000001",
        "issuer_name": "FERRETERIA EL TORNILLO SAS",
        "issuer_nit": "900123456-7",
        "receiver_name": "IKBO SAS",
        "receiver_nit": "901000001",
        "currency": "COP",
        "subtotal": 150000.0,
        "total_taxes": 28500.0,
        "total": 150000.0,
        "payment_type_id": 5636,
        "cost_center_id": 1235,
        "siigo_id": None,
        "accounting_locked": False,
        "accounting_error_class": None,
        "accounting_recommended_action": None,
        "accounting_attempts": 0,
        "siigo_name": None,
        "accounting_error": None,
        "details": [
            SimpleNamespace(
                id=11,
                code="51951001",
                type="Account",
                quantity=1,
                price=150000.0,
                description="Mantenimiento locativo",
                tax_id=13156,
            )
        ],
        "taxes": [SimpleNamespace(tax_id=1136, value=3750.0)],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _retencion(tax_id=1136, percentage=2.5, taxable_base=150000.0, value=3750.0):
    return SimpleNamespace(
        tax_id=tax_id, percentage=percentage, taxable_base=taxable_base, value=value
    )


class RepoFalso:
    def __init__(self, doc):
        self.doc = doc

    def get_by_id(self, document_id):
        return self.doc if self.doc and self.doc.id == document_id else None

    def claim_for_accounting(self, document_id, force=False):
        if self.doc.status != DocumentStatus.APROBADO:
            return None
        # El cerrojo es una columna, no un estado: el documento sigue viéndose como Aprobado
        # mientras se le envía. Los cinco estados funcionales no cambian por contabilizar.
        self.doc.accounting_locked = True
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
        self.doc.status = DocumentStatus.CONTABILIZADA
        self.doc.siigo_id = siigo_id
        self.doc.siigo_name = siigo_name
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
        # Cualquier fallo deja el documento en Error. Lo que decide `release` es el cerrojo.
        self.doc.status = DocumentStatus.ERROR
        self.doc.accounting_error = error
        self.doc.accounting_error_class = error_class
        self.doc.accounting_recommended_action = recommended_action
        if release:
            self.doc.accounting_locked = False
        return self.doc


class TaxRepoFalso:
    def __init__(self, taxes):
        self._taxes = taxes

    def list_by_document(self, document_id):
        return list(self._taxes)


class CatalogoFalso:
    def __init__(self, items):
        self._items = items

    def get_active(self):
        return self._items


class RagFalso:
    """Registra lo que se le pide indexar y retirar, sin hablar con nadie."""

    def __init__(self):
        self.indexed = []
        self.revoked = []

    def index_chunk_internal(self, **kwargs):
        self.indexed.append(kwargs)
        return {"id": 1}

    def revoke_chunks_internal(self, **kwargs):
        self.revoked.append(kwargs)
        return {"deleted": 1}


def _publicador(doc, rag, taxes=None):
    return AccountingKnowledgePublisher(
        rag_client=rag,
        tenant_slug="ikbo",
        document_repo=RepoFalso(doc),
        tax_repo=TaxRepoFalso(taxes if taxes is not None else [_retencion()]),
        integration_tax_repo=CatalogoFalso([SimpleNamespace(id=1136, name="ReteFuente servicios")]),
        cost_center_repo=CatalogoFalso([SimpleNamespace(id=1235, name="Administración")]),
    )


class SiigoFalso:
    def __init__(self, resultado):
        self.resultado = resultado
        self.enviados = []

    def create_purchase_invoice(self, payload):
        self.enviados.append(payload)
        return self.resultado


def _caso_de_uso(doc, rag, resultado):
    siigo = SiigoFalso(resultado)
    use_case = AccountDocumentUseCase(
        document_repo=RepoFalso(doc),
        parameters_provider=lambda: PARAMETROS,
        siigo_client=siigo,
        knowledge_publisher=_publicador(doc, rag),
    )
    return use_case, siigo


# ── Criterio: una causación no contabilizada NO es conocimiento ────────────────


@pytest.mark.parametrize(
    "estado",
    [DocumentStatus.PROCESADO, DocumentStatus.CAUSADO, DocumentStatus.APROBADO],
)
def test_documento_no_contabilizado_no_genera_conocimiento(estado):
    """Procesado, Causado y Aprobado son estados sin conocimiento, por definición del RF."""
    doc = _documento(status=estado)
    rag = RagFalso()

    publicado = _publicador(doc, rag).publish(document_id=1)

    assert publicado is False
    assert rag.indexed == []


def test_documento_marcado_contabilizado_sin_id_de_siigo_no_genera_conocimiento():
    """Sin `siigo_id` no consta contra qué comprobante real se contabilizó.

    Un documento en «Contabilizada» sin identificador es el síntoma de una contabilización
    que no terminó bien, no un caso del que se pueda aprender.
    """
    doc = _documento(status=DocumentStatus.CONTABILIZADA, siigo_id=None)
    rag = RagFalso()

    assert _publicador(doc, rag).publish(document_id=1) is False
    assert rag.indexed == []


def test_envio_fallido_a_siigo_no_alimenta_el_rag():
    """Aunque el documento estuviera aprobado, si SIIGO rechaza no hay nada que aprender."""
    doc = _documento()
    rag = RagFalso()
    use_case, _ = _caso_de_uso(
        doc,
        rag,
        PurchaseInvoiceResult(
            ok=False,
            siigo_id=None,
            error="Tercero inexistente",
            status_code=400,
            siigo_codes=["invalid_reference"],
        ),
    )

    outcome = use_case.execute(1)

    assert outcome.ok is False
    assert rag.indexed == []


def test_error_de_validacion_previo_al_envio_no_alimenta_el_rag():
    """Si ni siquiera se llamó a SIIGO, con más razón no hay conocimiento."""
    doc = _documento(details=[])
    rag = RagFalso()
    use_case, siigo = _caso_de_uso(doc, rag, PurchaseInvoiceResult(ok=True, siigo_id="SI-1"))

    outcome = use_case.execute(1)

    assert outcome.ok is False
    assert siigo.enviados == []
    assert rag.indexed == []


# ── Criterio: una causación contabilizada SÍ genera conocimiento ───────────────


def test_contabilizacion_exitosa_genera_conocimiento_validado():
    doc = _documento()
    rag = RagFalso()
    use_case, siigo = _caso_de_uso(
        doc,
        rag,
        PurchaseInvoiceResult(ok=True, siigo_id="a1b2c3", siigo_name="FC-1-101"),
    )

    outcome = use_case.execute(1)

    assert outcome.ok is True
    assert len(rag.indexed) == 1
    chunk = rag.indexed[0]
    assert chunk["is_validated"] is True
    assert chunk["siigo_id"] == "a1b2c3"
    assert chunk["source_type"] == "invoice"
    assert chunk["source_id"] == 1
    assert chunk["tenant_slug"] == "ikbo"


def test_el_conocimiento_es_la_causacion_final_enviada_a_siigo():
    """La cuenta que se indexa es la que viajó a SIIGO, no la que propuso la IA al principio.

    Se simula la corrección del contador cambiando la cuenta del detalle antes de
    contabilizar: el conocimiento debe contener la cuenta corregida.
    """
    doc = _documento()
    doc.details[0].code = "51101501"  # la cuenta que el contador dejó tras revisar
    rag = RagFalso()
    use_case, siigo = _caso_de_uso(doc, rag, PurchaseInvoiceResult(ok=True, siigo_id="a1b2c3"))

    use_case.execute(1)

    contenido = rag.indexed[0]["content"]
    assert "51101501" in contenido
    assert siigo.enviados[0]["items"][0]["code"] == "51101501"


def test_el_conocimiento_incluye_todo_lo_que_exige_el_rf():
    """Retención, tipo, base, tarifa, valor, cuenta, tercero y centro de costo."""
    doc = _documento(status=DocumentStatus.CONTABILIZADA, siigo_id="a1b2c3")
    contenido = build_accounted_knowledge_content(
        document=doc,
        taxes=[_retencion()],
        tax_name_map={1136: "ReteFuente servicios"},
        payload={
            "items": [
                {
                    "code": "51951001",
                    "description": "Mantenimiento locativo",
                    "quantity": 1,
                    "price": 150000.0,
                }
            ],
            "cost_center": 1235,
            "retention_ids": [1136],
        },
        siigo_id="a1b2c3",
        cost_center_name_map={1235: "Administración"},
    )

    assert "ReteFuente servicios" in contenido  # tipo / concepto de la retención
    assert "2.5%" in contenido  # tarifa
    assert "150000.0" in contenido  # base gravable
    assert "3750.0" in contenido  # valor retenido
    assert "51951001" in contenido  # cuenta contable
    assert "900123456-7" in contenido  # tercero
    assert "Administración" in contenido  # centro de costo
    assert "a1b2c3" in contenido  # comprobante de SIIGO
    assert "identificar documentos similares" in contenido


def test_sin_retenciones_tambien_es_conocimiento_util():
    """Que a un tercero no se le practique retención es información, no ausencia de ella."""
    doc = _documento(status=DocumentStatus.CONTABILIZADA, siigo_id="a1b2c3")
    contenido = build_accounted_knowledge_content(document=doc, taxes=[], siigo_id="a1b2c3")

    assert "Retenciones practicadas: ninguna." in contenido


# ── Criterio: una causación invalidada deja de ser referencia ──────────────────


def test_revocar_retira_el_conocimiento_del_documento():
    doc = _documento(status=DocumentStatus.CONTABILIZADA, siigo_id="a1b2c3")
    rag = RagFalso()

    assert _publicador(doc, rag).revoke(1, motivo="reversión") is True
    assert rag.revoked == [{"tenant_slug": "ikbo", "source_type": "invoice", "source_id": 1}]


# ── El aprendizaje no puede romper la contabilización ─────────────────────────


def test_un_fallo_del_rag_no_afecta_a_la_contabilizacion():
    """La factura ya existe en SIIGO: nada de lo que pase en el RAG puede deshacerla."""

    class RagRoto:
        def index_chunk_internal(self, **kwargs):
            raise RuntimeError("rag-service caído")

    doc = _documento()
    use_case = AccountDocumentUseCase(
        document_repo=RepoFalso(doc),
        parameters_provider=lambda: PARAMETROS,
        siigo_client=SiigoFalso(PurchaseInvoiceResult(ok=True, siigo_id="a1b2c3")),
        knowledge_publisher=_publicador(doc, RagRoto()),
    )

    outcome = use_case.execute(1)

    assert outcome.ok is True
    assert outcome.siigo_id == "a1b2c3"
