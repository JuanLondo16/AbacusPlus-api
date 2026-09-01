"""RF-02 — Las retenciones de un documento aprobado no se tocan.

Hueco de origen: al unificar la regla de edición se protegieron la cuenta PUC, el tipo de
pago y el centro de costo, pero los endpoints de retenciones se quedaron sin guarda. La
interfaz ocultaba los botones, pero una petición directa a la API podía agregar, modificar
o eliminar retenciones de una factura ya **Aprobada**.

Es el caso que más pesa de los cuatro: las retenciones cambian el **total a pagar**, así que
alterarlas después de aprobar cambia la cifra por la que el contador respondió.

Listar queda libre a propósito: es solo lectura y consultar una factura aprobada es legítimo.
"""

from datetime import date, datetime, timezone

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.adapters.api.document_guards import require_editable
from app.domain.value_objects.document_status import DocumentStatus
from app.infrastructure.persistence.models.document import Document
from fastapi import HTTPException


def _make_doc(status_code: int, **kwargs) -> Document:
    defaults = {
        "document_name": "test.xml",
        "document_number": "FBC-RF02",
        "date": date(2026, 6, 1),
        "hour": "10:00",
        "currency": "COP",
        "document_type": "Factura de venta",
        "uuid": f"uuid-rf02-{status_code}",
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
        "status": status_code,
    }
    defaults.update(kwargs)
    return Document(**defaults)


class TestRetentionEditGuard:
    @pytest.mark.parametrize(
        "estado",
        [DocumentStatus.PROCESADO, DocumentStatus.CAUSADO],
        ids=["procesado", "causado"],
    )
    def test_allows_editing_while_the_document_is_open(self, estado):
        require_editable(_make_doc(estado))  # no debe lanzar

    @pytest.mark.parametrize(
        "estado",
        [DocumentStatus.APROBADO, DocumentStatus.CONTABILIZADA, DocumentStatus.ERROR],
        ids=["aprobado", "contabilizada", "error"],
    )
    def test_blocks_editing_once_the_document_is_closed(self, estado):
        with pytest.raises(HTTPException) as exc:
            require_editable(_make_doc(estado))
        assert exc.value.status_code == 409

    def test_the_error_explains_how_to_unblock_it(self):
        """El 409 tiene que decir qué hacer, no solo que no se puede."""
        with pytest.raises(HTTPException) as exc:
            require_editable(_make_doc(DocumentStatus.APROBADO))
        detail = exc.value.detail
        assert "Aprobado" in detail
        assert "Cancele la aprobación" in detail

    def test_the_guard_is_the_same_one_the_other_endpoints_use(self):
        """Una sola definición: si alguien la duplica, este test deja de tener sentido.

        La cuenta PUC (RF-01), el tipo de pago y el centro de costo (RF-07) importan
        `require_editable` de este mismo módulo. Tener una copia por router fue lo que dejó
        a las retenciones sin protección.
        """
        from app.adapters.api.routers import document_taxes, documents

        assert documents._require_editable is require_editable
        assert document_taxes._require_editable is require_editable
