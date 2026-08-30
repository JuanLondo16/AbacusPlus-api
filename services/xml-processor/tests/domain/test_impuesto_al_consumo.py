"""El INC de una línea, visible por separado del IVA.

`tax_type`/`tax_value` solo conservan el impuesto PRINCIPAL de la línea —el de mayor
importe—, así que en las facturas de telecomunicaciones, que declaran IVA 19 % e INC 4 % en
el MISMO renglón, el impuesto al consumo no aparecía en ningún campo: para saber que estaba
había que abrir el XML. Sumarlo aparte es lo que permite al contador cuadrarlo contra su
cuenta contable.
"""

import pytest
from app.domain.services.line_taxes import (
    ESQUEMA_IVA,
    ESQUEMAS_DE_CONSUMO,
    desglose_de_impuesto,
    impuesto_al_consumo,
)


class TestQueCuentaComoConsumo:
    def test_el_inc_del_esquema_04(self):
        """El caso real de BEC520526814."""
        impuestos = [
            {"esquema": "01", "nombre": "IVA", "porcentaje": 19.0, "valor": 2370.25},
            {"esquema": "04", "nombre": "INC", "porcentaje": 4.0, "valor": 499.0},
        ]
        assert impuesto_al_consumo(impuestos) == 499.0

    def test_no_confunde_el_iva_con_el_consumo(self):
        assert impuesto_al_consumo([{"esquema": "01", "valor": 18919.75}]) == 0.0

    @pytest.mark.parametrize("esquema", sorted(ESQUEMAS_DE_CONSUMO))
    def test_los_tres_esquemas_de_consumo_cuentan(self, esquema):
        """«04» INC, «02» IC y «22» INC Bolsas son todos impuesto al consumo."""
        assert impuesto_al_consumo([{"esquema": esquema, "valor": 100.0}]) == 100.0

    def test_suma_varios_consumos_de_la_misma_linea(self):
        impuestos = [
            {"esquema": "04", "valor": 499.0},
            {"esquema": "22", "valor": 73.0},
        ]
        assert impuesto_al_consumo(impuestos) == 572.0


class TestCasosQueNoDebenRomper:
    def test_una_linea_sin_impuestos(self):
        assert impuesto_al_consumo(None) == 0.0
        assert impuesto_al_consumo([]) == 0.0

    def test_una_entrada_que_no_es_diccionario(self):
        assert impuesto_al_consumo(["basura", {"esquema": "04", "valor": 10.0}]) == 10.0

    def test_un_valor_ilegible_no_tumba_la_suma(self):
        """Un campo corrupto degrada a cero: la línea sigue contando lo que sí se pudo leer."""
        impuestos = [
            {"esquema": "04", "valor": "no es un número"},
            {"esquema": "04", "valor": 25.0},
        ]
        assert impuesto_al_consumo(impuestos) == 25.0

    def test_el_esquema_se_compara_sin_espacios_ni_minusculas(self):
        assert impuesto_al_consumo([{"esquema": " 04 ", "valor": 50.0}]) == 50.0


class TestDesgloseSeparadoDeIvaEInc:
    """Cada impuesto con SU tarifa y SU importe, sin que uno se lea con el nombre del otro.

    `tax_type`/`tax_value` guardan el impuesto PRINCIPAL de la línea —el de mayor importe—, no
    el IVA. La interfaz los pintaba bajo el rótulo «Tipo IVA», lo que en los datos reales del
    cliente producía dos errores distintos:

      · 3 líneas que solo llevan INC mostraban su tarifa (8 %) rotulada como IVA.
      · 9 líneas con IVA e INC dejaban el INC sin tarifa visible en ninguna parte.
    """

    IVA = {ESQUEMA_IVA}

    def test_sin_impuestos(self):
        for vacio in (None, []):
            assert desglose_de_impuesto(vacio, self.IVA) == (None, 0.0)
            assert desglose_de_impuesto(vacio, ESQUEMAS_DE_CONSUMO) == (None, 0.0)

    def test_solo_iva(self):
        linea = [{"esquema": "01", "porcentaje": 19.0, "valor": 18919.75}]
        assert desglose_de_impuesto(linea, self.IVA) == (19.0, 18919.75)
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (None, 0.0)

    def test_solo_inc(self):
        """El caso del documento 81: 8 % de INC que se mostraba como si fuera IVA."""
        linea = [{"esquema": "04", "porcentaje": 8.0, "valor": 2518.52}]
        assert desglose_de_impuesto(linea, self.IVA) == (None, 0.0)
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (8.0, 2518.52)

    def test_iva_e_inc_en_la_misma_linea(self):
        """El caso de BEC520526814: cada uno con su tarifa, ninguno pisando al otro."""
        linea = [
            {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25},
            {"esquema": "04", "porcentaje": 4.0, "valor": 499.0},
        ]
        assert desglose_de_impuesto(linea, self.IVA) == (19.0, 2370.25)
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (4.0, 499.0)

    def test_dos_inc_con_tarifas_distintas(self):
        """El importe suma; la tarifa queda vacía porque NO hay una sola que lo explique.

        Devolver 4 u 8 sería elegir una por el lector, que es exactamente inventarla.
        """
        linea = [
            {"esquema": "04", "porcentaje": 4.0, "valor": 100.0},
            {"esquema": "22", "porcentaje": 8.0, "valor": 50.0},
        ]
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (None, 150.0)

    def test_dos_inc_con_la_misma_tarifa_si_la_conservan(self):
        linea = [
            {"esquema": "04", "porcentaje": 8.0, "valor": 100.0},
            {"esquema": "04", "porcentaje": 8.0, "valor": 50.0},
        ]
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (8.0, 150.0)

    def test_impuesto_por_unidad_sin_porcentaje(self):
        """Un INC cobrado por unidad tiene importe pero no tarifa. No se inventa un 0 %."""
        linea = [{"esquema": "04", "porcentaje": 0.0, "por_unidad": 50.0, "valor": 146.0}]
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (None, 146.0)

    def test_valores_nulos_o_ausentes(self):
        linea = [{"esquema": "01"}, {"esquema": "04", "porcentaje": None, "valor": None}]
        assert desglose_de_impuesto(linea, self.IVA) == (None, 0.0)
        assert desglose_de_impuesto(linea, ESQUEMAS_DE_CONSUMO) == (None, 0.0)

    def test_una_entrada_ilegible_no_tumba_el_desglose(self):
        linea = ["basura", {"esquema": "01", "porcentaje": 19.0, "valor": 100.0}]
        assert desglose_de_impuesto(linea, self.IVA) == (19.0, 100.0)
