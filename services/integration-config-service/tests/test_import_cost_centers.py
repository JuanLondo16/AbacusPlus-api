"""Importación de centros de costo desde .xlsx.

La plantilla descargable usa encabezados en español (`código`, `nombre`, `id_externo`,
`activo`); el inglés (`code`, `name`, `external_id`, `active`) sigue aceptándose como
alias para no romper un archivo ya armado con él.
"""

from io import BytesIO

import pytest
from app.application.use_cases.import_cost_centers import ImportCostCentersUseCase
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


@pytest.fixture
def parser() -> ImportCostCentersUseCase:
    # `_parse_excel` es puro: no toca repositorio.
    return ImportCostCentersUseCase.__new__(ImportCostCentersUseCase)


class TestSpanishHeaders:
    def test_parses_minimal_file(self, parser):
        cost_centers = parser._parse_excel(
            _xlsx([("código", "nombre"), ("1112", "Administración")]), None
        )

        assert len(cost_centers) == 1
        assert cost_centers[0]["code"] == "1112"
        assert cost_centers[0]["name"] == "Administración"
        assert cost_centers[0]["external_id"] is None
        assert cost_centers[0]["active"] is True

    def test_parses_optional_columns(self, parser):
        cost_centers = parser._parse_excel(
            _xlsx(
                [
                    ("código", "nombre", "id_externo", "activo"),
                    ("1112", "Administración", "13222", "No"),
                ]
            ),
            None,
        )

        assert cost_centers[0]["external_id"] == "13222"
        assert cost_centers[0]["active"] is False

    def test_rejects_file_without_required_columns(self, parser):
        with pytest.raises(ValidationException, match="Missing required columns"):
            parser._parse_excel(_xlsx([("id_externo",), ("13222",)]), None)

    def test_rejects_duplicated_codes(self, parser):
        with pytest.raises(ValidationException, match="duplicated code"):
            parser._parse_excel(
                _xlsx(
                    [
                        ("código", "nombre"),
                        ("1112", "Administración"),
                        ("1112", "Administración otra vez"),
                    ]
                ),
                None,
            )


class TestEnglishHeaderAliases:
    """El encabezado con que este endpoint funcionaba antes sigue aceptándose."""

    def test_maps_english_headers(self, parser):
        cost_centers = parser._parse_excel(
            _xlsx(
                [
                    ("code", "name", "external_id", "active"),
                    ("1112", "Administración", "13222", "true"),
                ]
            ),
            None,
        )

        assert cost_centers[0]["code"] == "1112"
        assert cost_centers[0]["name"] == "Administración"
        assert cost_centers[0]["external_id"] == "13222"
        assert cost_centers[0]["active"] is True

    def test_spanish_canonical_header_wins_over_english_alias(self, parser):
        cost_centers = parser._parse_excel(
            _xlsx([("code", "nombre", "código"), ("OTRO", "Caja", "1112")]), None
        )

        assert cost_centers[0]["code"] == "1112"

    def test_codigo_without_accent_is_also_accepted(self, parser):
        cost_centers = parser._parse_excel(
            _xlsx([("codigo", "nombre"), ("1112", "Sin tilde")]), None
        )

        assert cost_centers[0]["code"] == "1112"
