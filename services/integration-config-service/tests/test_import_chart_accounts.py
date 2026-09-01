"""
Importación del plan de cuentas desde .xlsx.

Cubre en particular el formato de la exportación real de SIIGO, cuyos encabezados
vienen en español (`Código`, `Nombre`, `Activo`, …) y que no trae columna `level`.
"""

from io import BytesIO

import pytest
from app.application.use_cases.import_chart_accounts import ImportChartAccountsUseCase
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
def use_case() -> ImportChartAccountsUseCase:
    # `_parse_excel` es puro: no toca repositorio ni clientes HTTP.
    return ImportChartAccountsUseCase.__new__(ImportChartAccountsUseCase)


class TestCanonicalHeaders:
    def test_parses_minimal_file(self, use_case):
        accounts = use_case._parse_excel(
            _xlsx([("code", "name"), ("110505", "Caja general")]), None
        )

        assert len(accounts) == 1
        assert accounts[0]["code"] == "110505"
        assert accounts[0]["name"] == "Caja general"
        assert accounts[0]["active"] is True

    def test_rejects_file_without_required_columns(self, use_case):
        with pytest.raises(ValidationException, match="Missing required columns"):
            use_case._parse_excel(_xlsx([("cuenta", "descripcion"), ("1", "Activo")]), None)

    def test_rejects_duplicated_codes(self, use_case):
        with pytest.raises(ValidationException, match="duplicated code"):
            use_case._parse_excel(
                _xlsx([("code", "name"), ("110505", "Caja"), ("110505", "Caja otra vez")]), None
            )


class TestSpanishHeaderAliases:
    """La exportación de SIIGO trae los encabezados en español."""

    def test_maps_spanish_headers(self, use_case):
        accounts = use_case._parse_excel(
            _xlsx(
                [
                    ("Código", "Nombre", "Tipo de cuenta", "Activo"),
                    ("110505", "Caja general", "Activo", "Sí"),
                ]
            ),
            None,
        )

        assert accounts[0]["code"] == "110505"
        assert accounts[0]["name"] == "Caja general"
        assert accounts[0]["account_type"] == "Activo"
        assert accounts[0]["active"] is True

    def test_activo_no_marks_account_inactive(self, use_case):
        accounts = use_case._parse_excel(
            _xlsx([("Código", "Nombre", "Activo"), ("11050597", "D. fiscal caja general", "No")]),
            None,
        )

        assert accounts[0]["active"] is False

    def test_blank_activo_defaults_to_active(self, use_case):
        """Las cuentas de agrupación vienen con la columna vacía y deben quedar activas."""
        accounts = use_case._parse_excel(
            _xlsx([("Código", "Nombre", "Activo"), ("1105", "Caja", "")]), None
        )

        assert accounts[0]["active"] is True

    def test_canonical_header_wins_over_alias(self, use_case):
        accounts = use_case._parse_excel(
            _xlsx([("code", "name", "Código"), ("110505", "Caja", "OTRO")]), None
        )

        assert accounts[0]["code"] == "110505"

    def test_nivel_agrupacion_is_not_mistaken_for_level(self, use_case):
        """«Nivel agrupación» es texto («Transaccional»), no el nivel jerárquico."""
        accounts = use_case._parse_excel(
            _xlsx([("Código", "Nombre", "Nivel agrupación"), ("110505", "Caja", "Transaccional")]),
            None,
        )

        # No revienta al parsear y el nivel se infiere del código, no de esa columna.
        assert accounts[0]["level"] == 4

    def test_unrecognized_columns_are_kept_in_raw_payload(self, use_case):
        """Columnas reales de SIIGO sin equivalente en el modelo no se pierden en silencio."""
        accounts = use_case._parse_excel(
            _xlsx(
                [
                    (
                        "Código",
                        "Nombre",
                        "Categoría",
                        "Relación con",
                        "Maneja vencimientos",
                        "Diferencia fiscal",
                        "Nivel agrupación",
                    ),
                    (
                        "110505",
                        "Caja general",
                        "Caja - Bancos",
                        "Formas de pago",
                        "No maneja vencimiento",
                        "No",
                        "Transaccional",
                    ),
                ]
            ),
            None,
        )

        assert accounts[0]["raw_payload"]["categoría"] == "Caja - Bancos"
        assert accounts[0]["raw_payload"]["relación con"] == "Formas de pago"
        assert accounts[0]["raw_payload"]["maneja vencimientos"] == "No maneja vencimiento"
        assert accounts[0]["raw_payload"]["diferencia fiscal"] == "No"
        assert accounts[0]["raw_payload"]["nivel agrupación"] == "Transaccional"


class TestLevelDerivation:
    @pytest.mark.parametrize(
        "code,expected",
        [("1", 1), ("11", 2), ("1105", 3), ("110505", 4), ("11050501", 5), ("1105050101", 6)],
    )
    def test_derives_level_from_code_length(self, use_case, code, expected):
        accounts = use_case._parse_excel(_xlsx([("code", "name"), (code, "Cuenta")]), None)

        assert accounts[0]["level"] == expected

    def test_explicit_level_column_wins(self, use_case):
        accounts = use_case._parse_excel(
            _xlsx([("code", "name", "level"), ("110505", "Caja", 9)]), None
        )

        assert accounts[0]["level"] == 9

    def test_unexpected_code_length_yields_no_level(self, use_case):
        accounts = use_case._parse_excel(_xlsx([("code", "name"), ("110", "Rara")]), None)

        assert accounts[0]["level"] is None


class TestAcceptsMovements:
    """Una cuenta acepta movimientos solo si es hoja del árbol importado."""

    def test_only_leaves_accept_movements(self, use_case):
        recorded = {}

        class _Repo:
            def set_accepts_movements(self, movements):
                recorded.update(movements)

        use_case.repository = _Repo()
        use_case._recalculate_accepts_movements(
            [{"code": c} for c in ("1", "11", "1105", "110505", "11050501")]
        )

        assert recorded["11050501"] is True
        assert recorded["110505"] is False
        assert recorded["1105"] is False
        # Los códigos de menos de 4 dígitos nunca aceptan movimientos.
        assert recorded["1"] is False
        assert recorded["11"] is False
