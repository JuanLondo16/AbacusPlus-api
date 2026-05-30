"""
Regression tests for GET /documents status field type bug.

Root cause: documents.status was VARCHAR in tenant DBs; Pydantic status: int
field raised ValidationError → 500. Migration converts column to INTEGER.
"""
import pytest
from datetime import date, datetime, timezone

from pydantic import ValidationError

# All models must be imported before instantiating any SQLAlchemy model so that
# mapper relationships (e.g. DocumentDetail → ConceptDescription) can be resolved.
import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401

from app.application.dto.document import DocumentSummaryResponse
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository


def _make_doc(**kwargs) -> Document:
    defaults = dict(
        document_name="test.xml",
        document_number="FE001",
        date=date(2026, 5, 15),
        hour="10:00",
        currency="COP",
        document_type="Factura Electrónica",
        uuid="abc-123",
        issuer_name="PROVEEDOR S.A.S",
        issuer_nit="900123456",
        receiver_name="MI EMPRESA",
        receiver_nit="800987654",
        subtotal=100000.0,
        total_taxes=19000.0,
        retefuente=0.0,
        reteica=0.0,
        total=119000.0,
        register_at=datetime.now(timezone.utc),
        status=100,
    )
    defaults.update(kwargs)
    return Document(**defaults)


class TestDocumentSummaryResponseSerialization:
    """Guards against status type regression at the DTO layer."""

    def test_integer_status_serializes(self):
        doc = _make_doc(id=1, status=100)
        result = DocumentSummaryResponse.model_validate(doc, from_attributes=True)
        assert result.status == 100

    def test_all_valid_status_codes_serialize(self):
        for code in (0, 100, 200, 300, 400):
            doc = _make_doc(id=1, status=code)
            result = DocumentSummaryResponse.model_validate(doc, from_attributes=True)
            assert result.status == code

    def test_non_numeric_string_status_raises_validation_error(self):
        """Pre-migration VARCHAR values like 'Procesado' must fail with ValidationError."""
        doc = _make_doc(id=1, status="Procesado")
        with pytest.raises(ValidationError):
            DocumentSummaryResponse.model_validate(doc, from_attributes=True)


class TestGetDocumentsByDateRangeUseCase:
    def test_returns_documents_in_range(self, db_session):
        db_session.add(_make_doc(date=date(2026, 5, 15), status=100))
        db_session.commit()

        use_case = GetDocumentsByDateRangeUseCase(DocumentRepository(db_session))
        results = use_case.execute(date(2026, 5, 1), date(2026, 5, 31))

        assert len(results) == 1
        serialized = DocumentSummaryResponse.model_validate(results[0], from_attributes=True)
        assert serialized.status == 100
        assert serialized.document_number == "FE001"

    def test_excludes_documents_outside_range(self, db_session):
        db_session.add(_make_doc(date=date(2026, 4, 15)))
        db_session.commit()

        use_case = GetDocumentsByDateRangeUseCase(DocumentRepository(db_session))
        results = use_case.execute(date(2026, 5, 1), date(2026, 5, 31))

        assert len(results) == 0

    def test_filters_by_status(self, db_session):
        db_session.add(_make_doc(document_number="FE001", date=date(2026, 5, 10), status=100))
        db_session.add(_make_doc(document_number="FE002", date=date(2026, 5, 20), status=200))
        db_session.commit()

        use_case = GetDocumentsByDateRangeUseCase(DocumentRepository(db_session))
        results = use_case.execute(date(2026, 5, 1), date(2026, 5, 31), status=200)

        assert len(results) == 1
        assert results[0].status == 200

    def test_date_boundaries_inclusive(self, db_session):
        db_session.add(_make_doc(document_number="FE001", date=date(2026, 5, 1), status=100))
        db_session.add(_make_doc(document_number="FE002", date=date(2026, 5, 31), status=100))
        db_session.add(_make_doc(document_number="FE003", date=date(2026, 4, 30), status=100))
        db_session.add(_make_doc(document_number="FE004", date=date(2026, 6, 1), status=100))
        db_session.commit()

        use_case = GetDocumentsByDateRangeUseCase(DocumentRepository(db_session))
        results = use_case.execute(date(2026, 5, 1), date(2026, 5, 31))

        assert len(results) == 2
