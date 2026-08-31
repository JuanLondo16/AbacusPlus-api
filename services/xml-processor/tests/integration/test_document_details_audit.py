"""
RF-01 · La edición manual de una cuenta PUC debe dejar rastro en `document_field_changes`.

`PATCH /documents/{id}/details` recibe `DocumentDetailCodeUpdateItem`, cuyo identificador de
línea se llama `detail_id` (ver `app/application/dto/document.py`). `_auditar_correcciones`
buscaba en cambio la clave `id`, que ese DTO nunca tiene: `enviados.pop("id", None)` y
`getattr(asignacion, "id", None)` daban siempre `None`, `previos.get(None, {})` era siempre
`{}`, y `if campo not in anterior: continue` descartaba todos los campos antes de llegar a
`audit.record_field_change`. La escritura real de `code`/`code_source` en
`document_details` no se veía afectada —ocurre aparte, en `DocumentRepository`—, así que el
bug era silencioso: la cuenta cambiaba, pero ninguna corrección manual quedaba auditada.
"""

from datetime import date, datetime, timezone

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.adapters.api.routers.documents import _auditar_correcciones
from app.application.dto.document import DocumentDetailCodeUpdateItem
from app.infrastructure.persistence.models.accounting import DocumentFieldChange
from app.infrastructure.persistence.models.concept import ConceptDescription
from app.infrastructure.persistence.models.document import Document, DocumentDetail
from app.infrastructure.persistence.repositories.accounting_job_repository import (
    AccountingAuditRepository,
)


@pytest.fixture
def detail(db_session):
    concept = ConceptDescription(receiver_nit="800987654", description="Servicio de transporte")
    db_session.add(concept)
    db_session.flush()

    doc = Document(
        document_name="test.xml",
        document_number="FBC98359",
        date=date(2026, 4, 29),
        hour="10:00",
        currency="COP",
        document_type="Factura de venta",
        uuid="audit-rf01-123",
        issuer_name="BODEGA Y COCINA SAS",
        issuer_nit="830044885",
        receiver_name="MI EMPRESA",
        receiver_nit="800987654",
        subtotal=40000.0,
        total_taxes=7600.0,
        retefuente=0.0,
        reteica=0.0,
        total=47600.0,
        register_at=datetime.now(timezone.utc),
        status=200,
    )
    db_session.add(doc)
    db_session.flush()

    row = DocumentDetail(
        document_id=doc.id,
        description="Servicio De Transporte IVA",
        concept_description_id=concept.id,
        quantity=1,
        unit="und",
        price=40000.0,
        subtotal=40000.0,
        tax_type="19.0",
        tax_value=7600.0,
        total=47600.0,
        code="510505",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def audit(db_session):
    return AccountingAuditRepository(db_session)


class TestAuditaCorrecciones:
    def test_manual_edit_is_recorded_in_field_changes(self, detail, audit, db_session):
        """Antes del fix, esta llamada no escribía ninguna fila: `detail_id` no se leía."""
        previos = {detail.id: {"code": detail.code}}
        asignacion = DocumentDetailCodeUpdateItem(detail_id=detail.id, code="510506")

        _auditar_correcciones(
            audit=audit,
            document_id=detail.document_id,
            assignments=[asignacion],
            previos=previos,
            changed_by="contador@empresa.com",
            reason="causacion_edit",
        )

        cambios = db_session.query(DocumentFieldChange).all()
        assert len(cambios) == 1
        cambio = cambios[0]
        assert cambio.document_id == detail.document_id
        assert cambio.entity == "document_detail"
        assert cambio.entity_id == detail.id
        assert cambio.field == "code"
        assert cambio.old_value == "510505"
        assert cambio.new_value == "510506"
        assert cambio.changed_by == "contador@empresa.com"
        assert cambio.reason == "causacion_edit"

    def test_unchanged_value_is_not_recorded(self, detail, audit, db_session):
        previos = {detail.id: {"code": detail.code}}
        asignacion = DocumentDetailCodeUpdateItem(detail_id=detail.id, code="510505")

        _auditar_correcciones(
            audit=audit,
            document_id=detail.document_id,
            assignments=[asignacion],
            previos=previos,
            changed_by="contador@empresa.com",
            reason="causacion_edit",
        )

        assert db_session.query(DocumentFieldChange).count() == 0
