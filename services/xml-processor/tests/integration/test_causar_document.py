"""Transición Procesado (100) → Causado (200).

Bug de origen: la máquina de estados no tenía forma de salir de Procesado. Los documentos
nacían en 100 (`process_xml`), y los dos únicos casos de uso que escribían estado eran
`ApproveDocumentUseCase` (exige 200 → escribe 300) y `UnapproveDocumentUseCase` (exige 300
→ escribe 200). Ninguno aceptaba un documento en 100, así que Causado, Aprobado y
Contabilizado eran estados inalcanzables: en la base del tenant los 82 documentos estaban
en 100.

«Calcular contabilización» asignaba las cuentas PUC y respondía 200 OK —el botón «funciona»—
pero el documento se quedaba en Procesado, que es justo lo que reportó el usuario.
"""

from datetime import date, datetime, timezone

# Todos los modelos deben importarse antes de instanciar uno, para que SQLAlchemy resuelva
# las relaciones entre mappers (mismo requisito que el resto de tests de integración).
import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.application.use_cases.approve_document import (
    ApproveDocumentUseCase,
    CausarDocumentUseCase,
)
from app.domain.exceptions.base import EntityNotFoundException
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository


def _make_doc(**kwargs) -> Document:
    defaults = {
        "document_name": "test.xml",
        "document_number": "FE001",
        "date": date(2026, 6, 1),
        "hour": "10:00",
        "currency": "COP",
        "document_type": "Factura de venta",
        "uuid": "uuid-causar-1",
        "issuer_name": "PROVEEDOR S.A.S",
        "issuer_nit": "900123456",
        "receiver_name": "IKBO S.A.S",
        "receiver_nit": "901031352",
        "subtotal": 100000.0,
        "total_taxes": 19000.0,
        "retefuente": 0.0,
        "reteica": 0.0,
        "total": 119000.0,
        "register_at": datetime.now(timezone.utc),
        "status": DocumentStatus.PROCESADO,
    }
    defaults.update(kwargs)
    return Document(**defaults)


@pytest.fixture
def repo(db_session):
    return DocumentRepository(db_session)


class TestCausarDocument:
    def test_moves_a_processed_document_to_causado(self, db_session, repo):
        doc = _make_doc()
        db_session.add(doc)
        db_session.commit()

        result = CausarDocumentUseCase(document_repo=repo).execute(doc.id)

        assert result.status == DocumentStatus.CAUSADO

    def test_is_idempotent_when_already_causado(self, db_session, repo):
        """Recalcular un documento ya causado no debe fallar ni cambiar nada.

        El contador puede pulsar «Calcular contabilización» dos veces, o sobre una
        selección donde alguno ya pasó: eso no es un error que deba interrumpir el lote.
        """
        doc = _make_doc(uuid="uuid-causar-2", status=DocumentStatus.CAUSADO)
        db_session.add(doc)
        db_session.commit()

        result = CausarDocumentUseCase(document_repo=repo).execute(doc.id)

        assert result.status == DocumentStatus.CAUSADO

    def test_refuses_to_pull_back_an_approved_document(self, db_session, repo):
        """Causar no puede deshacer una aprobación: para eso está `unapprove`.

        Si causar degradara un Aprobado, recalcular por error revertiría trabajo ya
        confirmado por el contador sin avisar.
        """
        doc = _make_doc(uuid="uuid-causar-3", status=DocumentStatus.APROBADO)
        db_session.add(doc)
        db_session.commit()

        with pytest.raises(ValueError):
            CausarDocumentUseCase(document_repo=repo).execute(doc.id)

    def test_refuses_a_document_in_error(self, db_session, repo):
        doc = _make_doc(uuid="uuid-causar-4", status=DocumentStatus.ERROR)
        db_session.add(doc)
        db_session.commit()

        with pytest.raises(ValueError):
            CausarDocumentUseCase(document_repo=repo).execute(doc.id)

    def test_raises_when_the_document_does_not_exist(self, repo):
        with pytest.raises(EntityNotFoundException):
            CausarDocumentUseCase(document_repo=repo).execute(999999)

    def test_the_causado_document_can_then_be_approved(self, db_session, repo):
        """Cierra el ciclo: era imposible aprobar porque nada llegaba a Causado."""
        doc = _make_doc(uuid="uuid-causar-5")
        db_session.add(doc)
        db_session.commit()

        CausarDocumentUseCase(document_repo=repo).execute(doc.id)
        approved = ApproveDocumentUseCase(document_repo=repo).execute(doc.id)

        assert approved.status == DocumentStatus.APROBADO
