"""
RF-08 — Persistencia de las retenciones que la IA determina automáticamente.

Cuando la determinación corre durante el procesamiento del XML no hay interfaz esperando
la respuesta, así que la propuesta debe quedar guardada en el documento para que el
contador la vea en la sección de RF-02 y la confirme o la ajuste.

Esta ruta es interna (solo la consume el llm-service) y por eso concentra dos garantías
que no puede dar quien la llama: el origen `llm` se impone en el servidor, y reprocesar un
documento no duplica retenciones ni pisa las que el contador registró a mano.
"""

from datetime import date, datetime, timezone

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.adapters.api.routers.internal import (
    _verify_internal_secret,
    create_document_taxes_internal,
)
from app.application.dto.document_tax import DocumentTaxCreateRequest
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_tax_repository import (
    DocumentTaxRepository,
)
from fastapi import HTTPException


@pytest.fixture
def document(db_session):
    doc = Document(
        document_name="test.xml",
        document_number="FBC98359",
        date=date(2026, 4, 29),
        hour="10:00",
        currency="COP",
        document_type="Factura de venta",
        uuid="rf08-auto-1",
        issuer_name="BODEGA Y COCINA SAS",
        issuer_nit="830044885",
        receiver_name="MI EMPRESA",
        receiver_nit="800987654",
        subtotal=100000.0,
        total_taxes=19000.0,
        retefuente=0.0,
        reteica=0.0,
        total=119000.0,
        register_at=datetime.now(timezone.utc),
        status=200,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _retention(tax_id: int, source: str = "llm") -> DocumentTaxCreateRequest:
    return DocumentTaxCreateRequest(
        tax_id=tax_id, taxable_base=100000.0, percentage=2.5, source=source
    )


class TestPersistence:
    def test_saves_the_retentions_determined_by_the_model(self, document, db_session):
        result = create_document_taxes_internal(
            document.id, [_retention(10), _retention(11)], db=db_session
        )

        assert result.created == 2
        assert result.skipped == 0
        assert len(DocumentTaxRepository(db_session).list_by_document(document.id)) == 2

    def test_the_retained_value_is_derived_in_the_server(self, document, db_session):
        """El valor nunca llega del cliente: se calcula como base × porcentaje."""
        create_document_taxes_internal(document.id, [_retention(10)], db=db_session)

        row = DocumentTaxRepository(db_session).list_by_document(document.id)[0]
        assert row.value == 2500.0

    def test_a_missing_document_is_rejected(self, db_session):
        with pytest.raises(HTTPException) as exc:
            create_document_taxes_internal(999999, [_retention(10)], db=db_session)

        assert exc.value.status_code == 404


class TestOriginIsImposedByTheServer:
    def test_everything_saved_here_is_marked_as_coming_from_the_model(
        self, document, db_session
    ):
        """Es lo que permite a la interfaz distinguirlo del trabajo del contador."""
        create_document_taxes_internal(document.id, [_retention(10)], db=db_session)

        row = DocumentTaxRepository(db_session).list_by_document(document.id)[0]
        assert row.source == "llm"

    def test_a_client_cannot_disguise_a_suggestion_as_manual_work(
        self, document, db_session
    ):
        """Si el origen lo decidiera el cliente, una sugerencia podría hacerse pasar por
        trabajo manual y la interfaz dejaría de advertir antes de regenerarla."""
        create_document_taxes_internal(
            document.id, [_retention(10, source="manual")], db=db_session
        )

        row = DocumentTaxRepository(db_session).list_by_document(document.id)[0]
        assert row.source == "llm"


class TestIdempotency:
    def test_reprocessing_does_not_duplicate_retentions(self, document, db_session):
        create_document_taxes_internal(document.id, [_retention(10)], db=db_session)
        result = create_document_taxes_internal(document.id, [_retention(10)], db=db_session)

        assert result.created == 0
        assert result.skipped == 1
        assert len(DocumentTaxRepository(db_session).list_by_document(document.id)) == 1

    def test_a_repeated_id_within_one_batch_inserts_once(self, document, db_session):
        result = create_document_taxes_internal(
            document.id, [_retention(10), _retention(10)], db=db_session
        )

        assert result.created == 1
        assert result.skipped == 1

    def test_manual_work_of_the_accountant_is_never_overwritten(self, document, db_session):
        """Una retención registrada a mano sobre el mismo impuesto se conserva intacta."""
        repo = DocumentTaxRepository(db_session)
        repo.create(document.id, 10, 50000.0, 4.0, source="manual")

        result = create_document_taxes_internal(document.id, [_retention(10)], db=db_session)

        rows = repo.list_by_document(document.id)
        assert result.skipped == 1
        assert len(rows) == 1
        assert rows[0].source == "manual"
        assert rows[0].percentage == 4.0

    def test_only_the_new_ones_are_added(self, document, db_session):
        create_document_taxes_internal(document.id, [_retention(10)], db=db_session)
        result = create_document_taxes_internal(
            document.id, [_retention(10), _retention(11)], db=db_session
        )

        assert result.created == 1
        assert result.skipped == 1


class TestTheRouteIsNotPublic:
    """Escribe en los datos contables del tenant, así que exige el secreto compartido."""

    def test_a_wrong_secret_is_rejected(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SECRET", "el-secreto-real")

        with pytest.raises(HTTPException) as exc:
            _verify_internal_secret(x_internal_secret="otro")

        assert exc.value.status_code == 403

    def test_an_unset_secret_does_not_open_the_route(self, monkeypatch):
        """Sin secreto configurado la ruta se cierra, en vez de aceptar cualquier valor."""
        monkeypatch.delenv("INTERNAL_SECRET", raising=False)

        with pytest.raises(HTTPException) as exc:
            _verify_internal_secret(x_internal_secret="")

        assert exc.value.status_code == 403

    def test_the_right_secret_is_accepted(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SECRET", "el-secreto-real")

        assert _verify_internal_secret(x_internal_secret="el-secreto-real") is None

    def test_the_route_is_hidden_from_the_public_schema(self):
        """No debe aparecer en Swagger: no es parte del contrato público."""
        from app.adapters.api.routers.internal import router

        ruta = next(
            r for r in router.routes if r.path == "/internal/documents/{document_id}/taxes"
        )
        assert ruta.include_in_schema is False
