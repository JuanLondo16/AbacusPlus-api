import pytest
from datetime import date
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository


def _make_document(**overrides) -> Document:
    """Helper para crear un Document con valores por defecto validos."""
    defaults = dict(
        document_name="test.xml",
        document_number="FE-001",
        date=date(2024, 1, 15),
        hour="10:30:00",
        currency="COP",
        document_type="01",
        uuid="abc-123",
        issuer_name="Emisor",
        issuer_nit="900123456",
        issuer_phone="3001234567",
        issuer_email="emisor@test.com",
        receiver_name="Receptor",
        receiver_nit="800987654",
        receiver_phone="3009876543",
        receiver_email="receptor@test.com",
        subtotal=1000000.0,
        total_taxes=190000.0,
        total=1190000.0,
        status="Procesado",
    )
    defaults.update(overrides)
    return Document(**defaults)


class TestDocumentRepository:
    def test_create_document(self, db_session):
        repo = DocumentRepository(db_session)
        doc = _make_document()
        created = repo.create(doc)
        assert created.id is not None
        assert created.document_number == "FE-001"

    def test_get_by_document_number(self, db_session):
        repo = DocumentRepository(db_session)
        repo.create(_make_document(document_number="FE-002"))

        found = repo.get_by_document_number("FE-002")
        assert found is not None
        assert found.document_number == "FE-002"

    def test_get_by_document_number_not_found(self, db_session):
        repo = DocumentRepository(db_session)
        assert repo.get_by_document_number("NONEXISTENT") is None

    def test_get_by_id(self, db_session):
        repo = DocumentRepository(db_session)
        created = repo.create(_make_document(document_number="FE-003"))

        found = repo.get_by_id(created.id)
        assert found is not None
        assert found.id == created.id

    def test_get_by_id_not_found(self, db_session):
        repo = DocumentRepository(db_session)
        assert repo.get_by_id(99999) is None

    def test_get_by_date_range(self, db_session):
        repo = DocumentRepository(db_session)
        dates = [date(2024, 1, 10), date(2024, 1, 15), date(2024, 1, 20)]
        for i, d in enumerate(dates):
            repo.create(_make_document(
                document_number=f"FE-{i:03d}",
                document_name=f"test_{i}.xml",
                date=d,
                uuid=f"uuid-{i}",
            ))

        results = repo.get_by_date_range(date(2024, 1, 12), date(2024, 1, 18))
        assert len(results) == 1
        assert results[0].document_number == "FE-001"

    def test_get_by_date_range_empty(self, db_session):
        repo = DocumentRepository(db_session)
        results = repo.get_by_date_range(date(2025, 1, 1), date(2025, 12, 31))
        assert results == []
