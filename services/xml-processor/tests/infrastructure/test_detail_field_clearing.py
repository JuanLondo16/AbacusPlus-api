"""
Limpieza de asignaciones en una línea de detalle.

`update_detail_codes` decide qué escribir por la **presencia de la clave**, no por su valor.
Esa distinción es la que permite al contador quitar un centro de costo: enviar la clave en
`None` limpia el campo, mientras que omitirla lo conserva.

Antes se comprobaba `item.get(campo) is not None`, con lo cual un borrado era
indistinguible de un campo omitido y se descartaba en silencio: el usuario quitaba el
centro de costo, guardaba, y el valor anterior reaparecía al recargar.
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
    concept = ConceptDescription(receiver_nit="800987654", description="Servicio de refrigerio")
    db_session.add(concept)
    db_session.flush()

    doc = Document(
        document_name="test.xml",
        document_number="FBC98359",
        date=date(2026, 4, 29),
        hour="10:00",
        currency="COP",
        document_type="Factura de venta",
        uuid="clearing-123",
        issuer_name="BODEGA Y COCINA SAS",
        issuer_nit="830044885",
        receiver_name="MI EMPRESA",
        receiver_nit="800987654",
        subtotal=108600.0,
        total_taxes=20634.0,
        retefuente=0.0,
        reteica=0.0,
        total=129234.0,
        register_at=datetime.now(timezone.utc),
        status=200,
    )
    db_session.add(doc)
    db_session.flush()

    row = DocumentDetail(
        document_id=doc.id,
        description="Servicio De Refrigerio IVA",
        concept_description_id=concept.id,
        quantity=6,
        unit="und",
        price=18100.0,
        subtotal=108600.0,
        tax_type="19.0",
        tax_value=20634.0,
        total=129234.0,
        code="51956001",
        cost_center_id=5,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def repo(db_session):
    return DocumentRepository(db_session)


class TestClearing:
    def test_explicit_none_clears_the_cost_center(self, repo, detail, db_session):
        repo.update_detail_codes(
            [{"detail_id": detail.id, "cost_center_id": None}], code_source="manual"
        )
        db_session.refresh(detail)

        assert detail.cost_center_id is None

    def test_explicit_none_clears_the_account(self, repo, detail, db_session):
        repo.update_detail_codes([{"detail_id": detail.id, "code": None}], code_source="manual")
        db_session.refresh(detail)

        assert detail.code is None
        assert detail.code_source == "manual"

    def test_clearing_the_cost_center_leaves_the_account_untouched(self, repo, detail, db_session):
        repo.update_detail_codes(
            [{"detail_id": detail.id, "cost_center_id": None}], code_source="manual"
        )
        db_session.refresh(detail)

        assert detail.code == "51956001"

    def test_an_omitted_field_is_preserved(self, repo, detail, db_session):
        repo.update_detail_codes(
            [{"detail_id": detail.id, "code": "51956002"}], code_source="manual"
        )
        db_session.refresh(detail)

        assert detail.cost_center_id == 5

    def test_clearing_the_account_keeps_the_llm_suggestion_on_record(
        self, repo, detail, db_session
    ):
        repo.update_detail_codes([{"detail_id": detail.id, "code": "613505"}], code_source="llm")
        repo.update_detail_codes([{"detail_id": detail.id, "code": None}], code_source="manual")
        db_session.refresh(detail)

        assert detail.code is None
        assert detail.code_suggested == "613505"
