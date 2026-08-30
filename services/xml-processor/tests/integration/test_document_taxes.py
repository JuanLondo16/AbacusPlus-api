"""
RF-02 — Impuestos y retenciones a nivel de documento.

Cubre el ciclo completo del recurso `document_taxes`: agregar, listar, modificar y
eliminar retenciones (ReteFuente, ReteICA, ReteIVA, …), y la regla de negocio de que
el valor retenido siempre se deriva en el servidor de `base gravable × porcentaje`.
"""

from datetime import date, datetime, timezone

# Todos los modelos deben importarse antes de instanciar cualquier modelo SQLAlchemy
# para que las relaciones del mapper se resuelvan.
import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.application.dto.document_tax import compute_retention_value
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_tax_repository import (
    DocumentTaxRepository,
)


def _make_doc(**kwargs) -> Document:
    defaults = {
        "document_name": "test.xml",
        "document_number": "FBC98359",
        "date": date(2026, 4, 29),
        "hour": "10:00",
        "currency": "COP",
        "document_type": "Factura de venta",
        "uuid": "abc-123",
        "issuer_name": "BODEGA Y COCINA SAS",
        "issuer_nit": "830044885",
        "receiver_name": "MI EMPRESA",
        "receiver_nit": "800987654",
        "subtotal": 148600.0,
        "total_taxes": 28234.0,
        "retefuente": 0.0,
        "reteica": 0.0,
        "total": 176834.0,
        "register_at": datetime.now(timezone.utc),
        "status": 200,
    }
    defaults.update(kwargs)
    return Document(**defaults)


@pytest.fixture
def document(db_session):
    doc = _make_doc()
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


@pytest.fixture
def repo(db_session):
    return DocumentTaxRepository(db_session)


class TestComputeRetentionValue:
    """El valor retenido nunca lo envía el cliente: se calcula en el servidor."""

    def test_computes_percentage_of_base(self):
        assert compute_retention_value(100000.0, 2.5) == 2500.0

    def test_rounds_to_two_decimals(self):
        assert compute_retention_value(148600.0, 3.5) == 5201.0

    def test_zero_percentage_yields_zero(self):
        assert compute_retention_value(100000.0, 0.0) == 0.0

    def test_none_values_are_treated_as_zero(self):
        assert compute_retention_value(None, None) == 0.0


class TestRetentionSource:
    """RF-08: procedencia de la retención, equivalente de `code_source` en las líneas."""

    def test_defaults_to_manual(self, repo, document):
        """Sin origen declarado se asume trabajo del contador: es lo conservador."""
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        assert row.source == "manual"

    def test_records_an_accepted_suggestion_as_llm(self, repo, document):
        row = repo.create(
            document.id, tax_id=3, taxable_base=100000.0, percentage=2.5, source="llm"
        )

        assert row.source == "llm"

    @pytest.mark.parametrize("valor", ["LLM", "  llm  "])
    def test_normalizes_case_and_spacing(self, repo, document, valor):
        row = repo.create(
            document.id, tax_id=3, taxable_base=100000.0, percentage=2.5, source=valor
        )

        assert row.source == "llm"

    @pytest.mark.parametrize("valor", ["cualquier-cosa", "", "<script>", None])
    def test_unknown_values_fall_back_to_manual(self, repo, document, valor):
        """El origen lo declara el cliente, así que no se persiste tal cual."""
        row = repo.create(
            document.id, tax_id=3, taxable_base=100000.0, percentage=2.5, source=valor
        )

        assert row.source == "manual"


class TestDocumentTaxRepository:
    """CRUD de retenciones del documento — RF-02."""

    def test_create_persists_and_derives_value(self, repo, document):
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        assert row.id is not None
        assert row.document_id == document.id
        assert row.tax_id == 3
        assert row.value == 2500.0

    def test_list_by_document_returns_only_its_own_taxes(self, repo, document, db_session):
        other = _make_doc(uuid="def-456", document_number="FBC00002")
        db_session.add(other)
        db_session.commit()

        repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)
        repo.create(document.id, tax_id=4, taxable_base=100000.0, percentage=1.0)
        repo.create(other.id, tax_id=3, taxable_base=50000.0, percentage=2.5)

        rows = repo.list_by_document(document.id)
        assert len(rows) == 2
        assert {r.tax_id for r in rows} == {3, 4}

    def test_update_recalculates_value(self, repo, document):
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        updated = repo.update(document.id, row.id, taxable_base=200000.0)

        assert updated.taxable_base == 200000.0
        # El porcentaje se conserva y el valor se re-deriva.
        assert updated.percentage == 2.5
        assert updated.value == 5000.0

    def test_update_only_touches_provided_fields(self, repo, document):
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        updated = repo.update(document.id, row.id, percentage=4.0)

        assert updated.tax_id == 3
        assert updated.taxable_base == 100000.0
        assert updated.value == 4000.0

    def test_update_can_change_the_tax(self, repo, document):
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        updated = repo.update(document.id, row.id, tax_id=7, percentage=1.0)

        assert updated.tax_id == 7
        assert updated.value == 1000.0

    def test_update_returns_none_for_unknown_tax(self, repo, document):
        assert repo.update(document.id, 9999, percentage=1.0) is None

    def test_update_returns_none_when_tax_belongs_to_another_document(
        self, repo, document, db_session
    ):
        other = _make_doc(uuid="def-456", document_number="FBC00002")
        db_session.add(other)
        db_session.commit()
        row = repo.create(other.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        assert repo.update(document.id, row.id, percentage=1.0) is None

    def test_delete_removes_the_row(self, repo, document):
        row = repo.create(document.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        assert repo.delete(document.id, row.id) is True
        assert repo.list_by_document(document.id) == []

    def test_delete_returns_false_for_unknown_tax(self, repo, document):
        assert repo.delete(document.id, 9999) is False

    def test_delete_does_not_cross_documents(self, repo, document, db_session):
        other = _make_doc(uuid="def-456", document_number="FBC00002")
        db_session.add(other)
        db_session.commit()
        row = repo.create(other.id, tax_id=3, taxable_base=100000.0, percentage=2.5)

        assert repo.delete(document.id, row.id) is False
        assert len(repo.list_by_document(other.id)) == 1
