"""Importación de productos/servicios desde .xlsx, incluido el parámetro `mode` del endpoint
`POST /integrations/products/imports` (`upsert`/`replace`) que expone el router.
"""

import itertools
from datetime import datetime, timezone
from io import BytesIO

import pytest
from app.application.use_cases.import_products import ImportProductsUseCase
from app.domain.exceptions.base import ValidationException
from openpyxl import Workbook


def _xlsx(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class _FakeRepository:
    """Repositorio en memoria: registra con qué `replace` se llamó `upsert_many` y devuelve
    filas con la forma que espera `ProductResponse` (id/synced_at/raw_payload incluidos), para
    que `ImportProductsUseCase.execute` pueda construir la respuesta real."""

    def __init__(self):
        self.upsert_calls: list[tuple[list[dict], bool]] = []
        self.stored: list[dict] = []
        self._next_id = itertools.count(1)

    def upsert_many(self, products, replace: bool = False) -> int:
        items = list(products)
        self.upsert_calls.append((items, replace))
        if replace:
            self.stored = []
        now = datetime.now(timezone.utc)
        for item in items:
            self.stored.append(
                {
                    "id": next(self._next_id),
                    "code": item["code"],
                    "type": item["type"],
                    "description": item["description"],
                    "active": item.get("active", True),
                    "synced_at": now,
                    "raw_payload": item.get("raw_payload", {}),
                }
            )
        return len(items)

    def list(self, active=None):
        return self.stored


@pytest.fixture
def parser() -> ImportProductsUseCase:
    # `_parse_excel` es puro: no toca repositorio.
    return ImportProductsUseCase.__new__(ImportProductsUseCase)


class TestParseExcel:
    def test_parses_minimal_file(self, parser):
        products = parser._parse_excel(
            _xlsx([("code", "type", "description"), ("P-001", "product", "Licencia anual")]),
            None,
        )

        assert len(products) == 1
        assert products[0]["code"] == "P-001"
        assert products[0]["type"] == "product"
        assert products[0]["description"] == "Licencia anual"
        assert products[0]["active"] is True

    def test_rejects_file_without_required_columns(self, parser):
        with pytest.raises(ValidationException, match="Missing required columns"):
            parser._parse_excel(_xlsx([("codigo", "tipo"), ("x", "y")]), None)

    def test_rejects_duplicated_codes(self, parser):
        with pytest.raises(ValidationException, match="duplicated code"):
            parser._parse_excel(
                _xlsx(
                    [
                        ("code", "type", "description"),
                        ("P-001", "product", "Uno"),
                        ("P-001", "service", "Otro"),
                    ]
                ),
                None,
            )

    def test_rejects_invalid_type(self, parser):
        with pytest.raises(ValidationException, match="type must be 'producto'/'product'"):
            parser._parse_excel(
                _xlsx([("code", "type", "description"), ("P-001", "gadget", "Algo")]), None
            )

    def test_active_defaults_to_true_when_blank(self, parser):
        products = parser._parse_excel(
            _xlsx(
                [("code", "type", "description", "active"), ("P-001", "service", "Soporte", "")]
            ),
            None,
        )

        assert products[0]["active"] is True


class TestSpanishHeadersAndValues:
    """La plantilla descargable usa encabezados y valores en español; el inglés sigue
    aceptándose como alias para no romper un archivo ya armado con él."""

    def test_maps_spanish_headers(self, parser):
        products = parser._parse_excel(
            _xlsx(
                [
                    ("código", "tipo", "descripción", "activo"),
                    ("P-001", "producto", "Licencia anual", "Sí"),
                ]
            ),
            None,
        )

        assert products[0]["code"] == "P-001"
        assert products[0]["type"] == "product"
        assert products[0]["description"] == "Licencia anual"
        assert products[0]["active"] is True

    def test_accepts_servicio_as_service(self, parser):
        products = parser._parse_excel(
            _xlsx([("código", "tipo", "descripción"), ("P-002", "servicio", "Soporte")]), None
        )

        assert products[0]["type"] == "service"

    def test_codigo_without_accent_is_also_accepted(self, parser):
        products = parser._parse_excel(
            _xlsx([("codigo", "tipo", "descripcion"), ("P-003", "producto", "Sin tilde")]), None
        )

        assert products[0]["code"] == "P-003"
        assert products[0]["description"] == "Sin tilde"


class TestExecuteMode:
    """`mode` decide si el repositorio hace upsert incremental o reemplaza todo el catálogo."""

    def _use_case_with_repo(self, repo):
        use_case = ImportProductsUseCase.__new__(ImportProductsUseCase)
        use_case.repository = repo
        return use_case

    def test_default_mode_is_upsert(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        use_case.execute(
            file_content=_xlsx([("code", "type", "description"), ("P-001", "product", "X")])
        )

        assert repo.upsert_calls[-1][1] is False

    def test_mode_replace_passes_replace_true_to_repository(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        use_case.execute(
            file_content=_xlsx([("code", "type", "description"), ("P-001", "product", "X")]),
            mode="replace",
        )

        assert repo.upsert_calls[-1][1] is True

    def test_invalid_mode_is_rejected_before_touching_the_repository(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        with pytest.raises(ValidationException, match="mode must be 'upsert' or 'replace'"):
            use_case.execute(
                file_content=_xlsx(
                    [("code", "type", "description"), ("P-001", "product", "X")]
                ),
                mode="wipe",
            )

        assert repo.upsert_calls == []

    def test_execute_returns_imported_count_and_listing(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        result = use_case.execute(
            file_content=_xlsx([("code", "type", "description"), ("P-001", "product", "X")])
        )

        assert result.imported == 1
        assert len(result.products) == 1
        assert result.products[0].code == "P-001"
        assert result.products[0].type == "product"
