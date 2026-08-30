"""La tarifa del ICA se publica POR MIL; la de las demás retenciones, en porcentaje.

Los municipios fijan el ICA por mil —Bogotá servicios 9,66 por mil— y el catálogo de SIIGO
sincroniza esa cifra tal cual: «ReteICA 9.66». Dividir esa tarifa entre 100, como si fuera un
porcentaje, retiene diez veces de más sobre dinero de un tercero.

Se detectó comparando lo que Abacus registraba con lo que SIIGO practicó en el documento
FC55130:

    ReteICA 7,66 sobre 110.554,62 → Abacus 8.468,48   SIIGO 846,85
    ReteIVA 15   sobre  21.005,38 → Abacus 3.150,81   SIIGO 3.150,81

La ReteIVA coincidía al céntimo porque su tarifa sí es un porcentaje. Solo el ICA cambia de
unidad, y por eso el divisor depende del tipo y no del importe ni del documento.
"""

import pytest
from app.application.dto.document_tax import (
    compute_retention_value,
    divisor_de_la_tarifa,
)


class TestReteICA:
    def test_la_tarifa_del_ica_se_lee_por_mil(self):
        """El caso real: SIIGO practicó 846,85, no 8.468,48."""
        assert compute_retention_value(110554.62, 7.66, "ReteICA") == 846.85

    def test_no_se_confunde_con_el_porcentaje(self):
        por_mil = compute_retention_value(110554.62, 7.66, "ReteICA")
        como_porcentaje = compute_retention_value(110554.62, 7.66, "ReteIVA")

        assert como_porcentaje == pytest.approx(por_mil * 10, abs=0.05)

    def test_el_tipo_se_compara_sin_distinguir_mayusculas(self):
        for tipo in ("ReteICA", "reteica", "RETEICA", " ReteICA "):
            assert compute_retention_value(110554.62, 7.66, tipo) == 846.85

    def test_bogota_servicios(self):
        """9,66 por mil sobre un millón son 9.660, no 96.600."""
        assert compute_retention_value(1_000_000.0, 9.66, "ReteICA") == 9660.0


class TestLasDemasRetenciones:
    def test_la_reteiva_sigue_siendo_porcentaje(self):
        """Coincidía con SIIGO antes del cambio y debe seguir coincidiendo."""
        assert compute_retention_value(21005.38, 15.0, "ReteIVA") == 3150.81

    def test_la_retefuente_sigue_siendo_porcentaje(self):
        assert compute_retention_value(100000.0, 2.5, "Retefuente") == 2500.0

    def test_sin_tipo_se_conserva_el_comportamiento_anterior(self):
        """La firma admite dos argumentos para no romper a quien ya la llamaba así."""
        assert compute_retention_value(100000.0, 2.5) == 2500.0

    def test_un_tipo_desconocido_no_cambia_de_unidad(self):
        assert compute_retention_value(100000.0, 2.5, "Impoconsumo") == 2500.0


class TestDivisor:
    @pytest.mark.parametrize("tipo", ["ReteICA", "reteica", "  RETEICA  "])
    def test_el_ica_divide_entre_mil(self, tipo):
        assert divisor_de_la_tarifa(tipo) == 1000

    @pytest.mark.parametrize("tipo", ["ReteIVA", "Retefuente", "Autorretencion", "", None])
    def test_el_resto_divide_entre_cien(self, tipo):
        assert divisor_de_la_tarifa(tipo) == 100


class TestElRedondeoNoCambia:
    """El cambio es de unidad, no de aritmética: se conserva HALF_UP en Decimal."""

    def test_redondea_hacia_arriba_en_el_medio_exacto(self):
        assert compute_retention_value(1000.0, 31.4715, "ReteIVA") == 314.72

    def test_una_base_en_cero_no_retiene(self):
        assert compute_retention_value(0.0, 7.66, "ReteICA") == 0.0

    def test_una_tarifa_en_cero_no_retiene(self):
        assert compute_retention_value(110554.62, 0.0, "ReteICA") == 0.0


class TestTodosLosTiposDelCatalogo:
    """Los seis tipos que sincroniza SIIGO, con la unidad declarada para cada uno.

    Se comprueban todos y no solo el ICA: dejar un tipo sin declarar es lo que produjo este
    fallo, y un tipo que hereda en silencio el divisor de otro no se manifiesta como error
    sino como una cifra plausible diez veces mayor.
    """

    @pytest.mark.parametrize(
        "tipo,tarifa,base,esperado",
        [
            # Tarifas reales del catálogo de la empresa.
            ("ReteICA", 11.04, 1_000_000.0, 11040.0),   # por mil
            ("ReteICA", 4.14, 1_000_000.0, 4140.0),     # por mil
            ("Retefuente", 11.0, 1_000_000.0, 110000.0),
            ("Retefuente", 2.5, 1_000_000.0, 25000.0),
            ("ReteIVA", 15.0, 1_000_000.0, 150000.0),
            ("Autorretencion", 1.1, 1_000_000.0, 11000.0),
            ("IVA", 19.0, 1_000_000.0, 190000.0),
            ("IVA", 5.0, 1_000_000.0, 50000.0),
            ("Impoconsumo", 8.0, 1_000_000.0, 80000.0),
        ],
    )
    def test_cada_tipo_usa_su_unidad(self, tipo, tarifa, base, esperado):
        assert compute_retention_value(base, tarifa, tipo) == esperado

    def test_solo_el_ica_se_lee_por_mil(self):
        """Si otro tipo cambiara de unidad, esta prueba lo delata."""
        for tipo in ("Retefuente", "ReteIVA", "Autorretencion", "IVA", "Impoconsumo"):
            assert divisor_de_la_tarifa(tipo) == 100, tipo
        assert divisor_de_la_tarifa("ReteICA") == 1000

    def test_las_variantes_del_catalogo_normalizan_igual(self):
        """El catálogo escribe «Autorretencion» y «autorretención.» para lo mismo."""
        assert divisor_de_la_tarifa("autorretención.") == divisor_de_la_tarifa("Autorretencion")

    def test_un_tipo_no_declarado_asume_porcentaje_y_avisa(self, caplog):
        """No se inventa una unidad, pero el caso queda registrado para revisarlo."""
        with caplog.at_level("WARNING"):
            assert divisor_de_la_tarifa("ReteCREE") == 100

        assert any("no tiene una unidad declarada" in r.message for r in caplog.records)

    def test_sin_tipo_no_se_avisa(self):
        """Llamar sin tipo es el modo compatible, no una omisión que reportar."""
        assert divisor_de_la_tarifa(None) == 100
        assert divisor_de_la_tarifa("") == 100
