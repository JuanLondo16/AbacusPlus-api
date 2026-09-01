"""Importación de tipos de pago desde .xlsx, incluido el parámetro `mode` del endpoint
`POST /integrations/payment-types/imports` (`upsert`/`replace`) que expone el router.
"""

import itertools
from datetime import datetime, timezone
from io import BytesIO

import pytest
from app.application.use_cases.import_payment_types import ImportPaymentTypesUseCase
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
    filas con la forma que espera `PaymentTypeResponse` (id/created_at/updated_at incluidos),
    para que `ImportPaymentTypesUseCase.execute` pueda construir la respuesta real."""

    def __init__(self):
        self.upsert_calls: list[tuple[list[dict], bool]] = []
        self.stored: list[dict] = []
        self._next_id = itertools.count(1)

    def upsert_many(self, payment_types, replace: bool = False) -> int:
        items = list(payment_types)
        self.upsert_calls.append((items, replace))
        if replace:
            self.stored = []
        now = datetime.now(timezone.utc)
        for item in items:
            self.stored.append(
                {
                    "id": next(self._next_id),
                    "name": item["name"],
                    "type": item["type"],
                    "active": item.get("active", True),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return len(items)

    def list(self, active=None):
        return self.stored


@pytest.fixture
def parser() -> ImportPaymentTypesUseCase:
    # `_parse_excel` es puro: no toca repositorio.
    return ImportPaymentTypesUseCase.__new__(ImportPaymentTypesUseCase)


class TestParseExcel:
    def test_parses_minimal_file(self, parser):
        payment_types = parser._parse_excel(
            _xlsx([("name", "type"), ("Transferencia", "electronico")]), None
        )

        assert len(payment_types) == 1
        assert payment_types[0]["name"] == "Transferencia"
        assert payment_types[0]["type"] == "electronico"
        assert payment_types[0]["active"] is True

    def test_rejects_file_without_required_columns(self, parser):
        with pytest.raises(ValidationException, match="Missing required columns"):
            parser._parse_excel(_xlsx([("nombre", "categoria"), ("x", "y")]), None)

    def test_rejects_duplicated_names(self, parser):
        with pytest.raises(ValidationException, match="duplicated name"):
            parser._parse_excel(
                _xlsx(
                    [
                        ("name", "type"),
                        ("Efectivo", "manual"),
                        ("Efectivo", "manual"),
                    ]
                ),
                None,
            )

    def test_active_defaults_to_true_when_blank(self, parser):
        payment_types = parser._parse_excel(
            _xlsx([("name", "type", "active"), ("Efectivo", "manual", "")]), None
        )

        assert payment_types[0]["active"] is True

    def test_active_accepts_falsy_spanish_values(self, parser):
        payment_types = parser._parse_excel(
            _xlsx([("name", "type", "active"), ("Efectivo", "manual", "no")]), None
        )

        assert payment_types[0]["active"] is False


class TestExecuteMode:
    """`mode` decide si el repositorio hace upsert incremental o reemplaza todo el catálogo."""

    def _use_case_with_repo(self, repo):
        use_case = ImportPaymentTypesUseCase.__new__(ImportPaymentTypesUseCase)
        use_case.repository = repo
        return use_case

    def test_default_mode_is_upsert(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        use_case.execute(file_content=_xlsx([("name", "type"), ("Efectivo", "manual")]))

        assert repo.upsert_calls[-1][1] is False

    def test_mode_replace_passes_replace_true_to_repository(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        use_case.execute(
            file_content=_xlsx([("name", "type"), ("Efectivo", "manual")]), mode="replace"
        )

        assert repo.upsert_calls[-1][1] is True

    def test_invalid_mode_is_rejected_before_touching_the_repository(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        with pytest.raises(ValidationException, match="mode must be 'upsert' or 'replace'"):
            use_case.execute(
                file_content=_xlsx([("name", "type"), ("Efectivo", "manual")]),
                mode="delete-everything",
            )

        assert repo.upsert_calls == []

    def test_execute_returns_imported_count_and_listing(self):
        repo = _FakeRepository()
        use_case = self._use_case_with_repo(repo)

        result = use_case.execute(
            file_content=_xlsx([("name", "type"), ("Efectivo", "manual")])
        )

        assert result.imported == 1
        assert len(result.payment_types) == 1
        assert result.payment_types[0].name == "Efectivo"
        assert result.payment_types[0].type == "manual"
