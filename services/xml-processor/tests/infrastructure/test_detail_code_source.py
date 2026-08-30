"""
RF-04 · Los tres estados de la cuenta de una línea de detalle.

`code`, `code_source` y `code_suggested` se combinan para distinguir:

- valor original      → `code_source` es None (el XML de la DIAN no trae cuenta PUC)
- sugerido por el LLM → `code_source == "llm"` y `code == code_suggested`
- editado a mano      → `code_source == "manual"` y `code != code_suggested`

La propuesta del modelo se conserva tras una edición manual: es lo que permite mostrar
al contador qué había sugerido el LLM y detectar sin ambigüedad el cambio manual.
"""

from datetime import date, datetime, timezone

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.infrastructure.persistence.models.concept import ConceptDescription
from app.infrastructure.persistence.models.document import Document, DocumentDetail
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository


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
        uuid="abc-123",
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
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def repo(db_session):
    return DocumentRepository(db_session)


class TestOriginalState:
    def test_a_new_line_has_no_account_and_no_source(self, detail):
        assert detail.code is None
        assert detail.code_source is None
        assert detail.code_suggested is None


class TestLlmSuggestion:
    def test_llm_assignment_records_source_and_suggestion(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        db_session.refresh(detail)

        assert detail.code == "613505"
        assert detail.code_source == "llm"
        # En estado «sugerido», el valor efectivo y la propuesta coinciden.
        assert detail.code_suggested == "613505"

    def test_regenerating_replaces_both(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        repo.update_detail_codes([{"detail_id": detail.id, "code": "618001"}], code_source="llm")
        db_session.refresh(detail)

        assert detail.code == "618001"
        assert detail.code_suggested == "618001"


class TestManualEdit:
    def test_manual_edit_keeps_the_llm_suggestion(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        repo.update_detail_codes([{"detail_id": detail.id, "code": "999999"}], code_source="manual")
        db_session.refresh(detail)

        assert detail.code == "999999"
        assert detail.code_source == "manual"
        # La propuesta del modelo sobrevive: así se detecta el cambio manual.
        assert detail.code_suggested == "613505"
        assert detail.code != detail.code_suggested

    def test_manual_edit_without_previous_suggestion(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "999999"}], code_source="manual")
        db_session.refresh(detail)

        assert detail.code_source == "manual"
        assert detail.code_suggested is None

    def test_accepting_a_new_suggestion_clears_the_manual_state(self, repo, detail, db_session):
        """Tras confirmar «Sí, volver a generar», la línea vuelve al estado sugerido."""
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        repo.update_detail_codes([{"detail_id": detail.id, "code": "999999"}], code_source="manual")
        repo.update_detail_codes([{"detail_id": detail.id, "code": "618001"}], code_source="llm")
        db_session.refresh(detail)

        assert detail.code == "618001"
        assert detail.code_source == "llm"
        assert detail.code_suggested == "618001"


class TestSourceIsNotTouchedByOtherFields:
    def test_updating_only_the_cost_center_preserves_the_state(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        repo.update_detail_codes(
            [{"detail_id": detail.id, "cost_center_id": 7}], code_source="manual"
        )
        db_session.refresh(detail)

        assert detail.cost_center_id == 7
        # Cambiar el centro de costo no convierte la cuenta en una edición manual.
        assert detail.code_source == "llm"
        assert detail.code_suggested == "613505"
