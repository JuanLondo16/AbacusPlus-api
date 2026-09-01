"""El parámetro `mode` (`upsert`/`replace`) del multipart/form-data llega intacto desde el
`POST /integrations/<recurso>/imports` hasta `<UseCase>.execute(...)`.

Los tests de `test_import_payment_types.py` / `test_import_products.py` prueban el use case en
aislamiento; estos prueban el cableado FastAPI (`Form(...)` -> `execute(mode=...)`) que es
justamente la parte nueva de cada router. Se usa `app.dependency_overrides` para no requerir
Postgres ni un JWT real: se reemplaza el use case por un doble que solo registra la llamada, y
`require_write` por un no-op (su propio comportamiento ya está cubierto en
`test_role_guard.py`).
"""

import pytest


@pytest.fixture
def app_and_overrides(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "secreto-de-prueba")
    from app.main import app

    yield app
    app.dependency_overrides.clear()


class _RecordingUseCase:
    def __init__(self, response):
        self.calls: list[dict] = []
        self._response = response

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _minimal_xlsx() -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestPaymentTypesModeWiring:
    def test_mode_replace_reaches_the_use_case(self, app_and_overrides):
        from app.application.dto.payment_type import ImportPaymentTypesResponse
        from app.adapters.api.routers.payment_types import (
            get_import_payment_types_use_case,
            require_write,
        )
        from fastapi.testclient import TestClient

        app = app_and_overrides
        fake = _RecordingUseCase(ImportPaymentTypesResponse(imported=0, payment_types=[]))
        app.dependency_overrides[get_import_payment_types_use_case] = lambda: fake
        app.dependency_overrides[require_write] = lambda: None
        client = TestClient(app)

        response = client.post(
            "/api/v1/integrations/payment-types/imports",
            files={"file": ("tipos.xlsx", _minimal_xlsx())},
            data={"mode": "replace"},
        )

        assert response.status_code == 200
        assert fake.calls[-1]["mode"] == "replace"

    def test_mode_defaults_to_upsert_when_omitted(self, app_and_overrides):
        from app.application.dto.payment_type import ImportPaymentTypesResponse
        from app.adapters.api.routers.payment_types import (
            get_import_payment_types_use_case,
            require_write,
        )
        from fastapi.testclient import TestClient

        app = app_and_overrides
        fake = _RecordingUseCase(ImportPaymentTypesResponse(imported=0, payment_types=[]))
        app.dependency_overrides[get_import_payment_types_use_case] = lambda: fake
        app.dependency_overrides[require_write] = lambda: None
        client = TestClient(app)

        response = client.post(
            "/api/v1/integrations/payment-types/imports",
            files={"file": ("tipos.xlsx", _minimal_xlsx())},
        )

        assert response.status_code == 200
        assert fake.calls[-1]["mode"] == "upsert"


class TestProductsModeWiring:
    def test_mode_replace_reaches_the_use_case(self, app_and_overrides):
        from app.application.dto.product import ImportProductsResponse
        from app.adapters.api.routers.products import (
            get_import_products_use_case,
            require_write,
        )
        from fastapi.testclient import TestClient

        app = app_and_overrides
        fake = _RecordingUseCase(ImportProductsResponse(imported=0, products=[]))
        app.dependency_overrides[get_import_products_use_case] = lambda: fake
        app.dependency_overrides[require_write] = lambda: None
        client = TestClient(app)

        response = client.post(
            "/api/v1/integrations/products/imports",
            files={"file": ("productos.xlsx", _minimal_xlsx())},
            data={"mode": "replace"},
        )

        assert response.status_code == 200
        assert fake.calls[-1]["mode"] == "replace"

    def test_mode_defaults_to_upsert_when_omitted(self, app_and_overrides):
        from app.application.dto.product import ImportProductsResponse
        from app.adapters.api.routers.products import (
            get_import_products_use_case,
            require_write,
        )
        from fastapi.testclient import TestClient

        app = app_and_overrides
        fake = _RecordingUseCase(ImportProductsResponse(imported=0, products=[]))
        app.dependency_overrides[get_import_products_use_case] = lambda: fake
        app.dependency_overrides[require_write] = lambda: None
        client = TestClient(app)

        response = client.post(
            "/api/v1/integrations/products/imports",
            files={"file": ("productos.xlsx", _minimal_xlsx())},
        )

        assert response.status_code == 200
        assert fake.calls[-1]["mode"] == "upsert"
