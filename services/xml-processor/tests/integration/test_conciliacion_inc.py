"""Conciliación: total de la factura, impuestos, retenciones y valor a pagar.

CASO REAL — BEC520526814 (COLOMBIA TELECOMUNICACIONES)

El XML de la DIAN declara la operación así, y es la fuente de verdad:

    LineExtensionAmount    112.052,63   base
    TaxInclusiveAmount     133.841,63   base + IVA 21.290,00 + INC 499,00
    PayableRoundingAmount        7,37   redondeo al peso, declarado por el emisor
    PayableAmount          133.849,00   total de la factura

SIIGO registró 129.074,00 cuando debía registrar 133.849,00 menos las retenciones. La
diferencia eran 499 pesos: el INC no llegaba a viajar y su importe se contaba igualmente al
anticipar el total, de modo que la línea de ajuste que debía compensarlo salía corta por esa
misma cantidad.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.domain.services.payload_line_taxes import impuestos_de_la_linea


def _peso(valor) -> Decimal:
    """Dos decimales, HALF_UP: la misma aritmética que usa el servicio para el dinero."""
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class _Linea:
    def __init__(self, taxes=None, tax_id=None, tax_type="0"):
        self.taxes = taxes
        self.tax_id = tax_id
        self.tax_type = tax_type


#: El catálogo del cliente el día del fallo: no existe ningún Impoconsumo del 4 %, pero sí un
#: «Retefuente 4 %», que es con quien enlazaba el INC.
CATALOGO_INCOMPLETO = {19.0: 20921, 4.0: 10599}
TIPOS_INCOMPLETO = {20921: "IVA", 10599: "Retefuente"}

#: El catálogo corregido, con el Impoconsumo que faltaba.
CATALOGO_COMPLETO = {19.0: 20921, 4.0: 10615}
TIPOS_COMPLETO = {20921: "IVA", 10615: "Impoconsumo"}

LINEA_1 = {"base": 99577.63, "iva": 18919.75}
LINEA_2 = {"base": 12475.00, "iva": 2370.25, "inc": 499.00}
TOTAL_DIAN = Decimal("133849.00")
REDONDEO_DIAN = Decimal("7.37")


def _linea_con_iva_e_inc(tax_id_inc, tax_id_fijado=20921):
    return _Linea(
        tax_id=tax_id_fijado,
        taxes=[
            {"esquema": "01", "porcentaje": 19.0, "valor": LINEA_2["iva"], "tax_id": 20921},
            {"esquema": "04", "porcentaje": 4.0, "valor": LINEA_2["inc"], "tax_id": tax_id_inc},
        ],
    )


class TestElCasoReal:
    def test_con_el_catalogo_incompleto_el_inc_no_viaja_y_no_se_cuenta(self):
        """La corrección del descuadre: lo que no viaja no puede contar en el total anticipado.

        Antes se contaban los 499 aunque el impuesto se descartara, así que la línea de ajuste
        salía de 7,37 en vez de 506,37 y SIIGO registraba 133.350,00.
        """
        ids, importe, avisos = impuestos_de_la_linea(
            _linea_con_iva_e_inc(10599), CATALOGO_INCOMPLETO, TIPOS_INCOMPLETO
        )
        assert ids == [20921], "una retención no puede viajar dentro de un ítem"
        assert _peso(importe) == _peso(LINEA_2["iva"])
        assert avisos

        lineas = _peso(LINEA_1["base"] + LINEA_1["iva"] + LINEA_2["base"]) + _peso(importe)
        ajuste = TOTAL_DIAN - lineas
        assert ajuste == _peso(LINEA_2["inc"]) + REDONDEO_DIAN == Decimal("506.37")
        assert lineas + ajuste == TOTAL_DIAN

    def test_con_el_catalogo_completo_el_inc_viaja_como_impuesto(self):
        """El arreglo de fondo: el INC deja de ser base gravable y el ajuste es solo el redondeo."""
        ids, importe, _ = impuestos_de_la_linea(
            _linea_con_iva_e_inc(10615), CATALOGO_COMPLETO, TIPOS_COMPLETO
        )
        assert ids == [20921, 10615]
        assert _peso(importe) == _peso(LINEA_2["iva"] + LINEA_2["inc"])

        lineas = _peso(LINEA_1["base"] + LINEA_1["iva"] + LINEA_2["base"]) + _peso(importe)
        ajuste = TOTAL_DIAN - lineas
        assert ajuste == REDONDEO_DIAN, "el único ajuste que queda es el redondeo de la DIAN"

    def test_la_conciliacion_completa_cuadra_con_la_factura(self):
        base = _peso(LINEA_1["base"] + LINEA_2["base"]) + REDONDEO_DIAN
        iva = _peso(LINEA_1["iva"] + LINEA_2["iva"])
        inc = _peso(LINEA_2["inc"])
        assert base + iva + inc == TOTAL_DIAN

        reteiva = _peso(iva * Decimal("15") / Decimal("100"))
        reteica = _peso(base * Decimal("9.66") / Decimal("1000"))
        assert reteiva == Decimal("3193.50")
        assert base + iva + inc - reteiva - reteica == Decimal("129573.00")


class TestCompatibilidad:
    def test_factura_sin_impuestos(self):
        ids, importe, _ = impuestos_de_la_linea(
            _Linea(taxes=None, tax_type="0"), CATALOGO_COMPLETO, TIPOS_COMPLETO
        )
        assert (ids, importe) == ([], 0.0)

    def test_factura_solo_con_iva(self):
        linea = _Linea(
            taxes=[{"esquema": "01", "porcentaje": 19.0, "valor": 190.0, "tax_id": 20921}]
        )
        ids, importe, _ = impuestos_de_la_linea(linea, CATALOGO_COMPLETO, TIPOS_COMPLETO)
        assert (ids, importe) == ([20921], 190.0)

    def test_factura_solo_con_inc(self):
        linea = _Linea(
            taxes=[{"esquema": "04", "porcentaje": 8.0, "valor": 2518.52, "tax_id": 10615}]
        )
        ids, importe, _ = impuestos_de_la_linea(linea, CATALOGO_COMPLETO, TIPOS_COMPLETO)
        assert (ids, importe) == ([10615], 2518.52)

    def test_varias_lineas_con_impuestos_distintos(self):
        lineas = [
            _Linea(taxes=[{"esquema": "01", "porcentaje": 19.0, "valor": 100.0, "tax_id": 20921}]),
            _Linea(taxes=[{"esquema": "04", "porcentaje": 8.0, "valor": 50.0, "tax_id": 10615}]),
            _Linea(taxes=None, tax_type="0"),
        ]
        total = sum(impuestos_de_la_linea(x, CATALOGO_COMPLETO, TIPOS_COMPLETO)[1] for x in lineas)
        assert _peso(total) == Decimal("150.00")

    def test_distintos_porcentajes_de_inc(self):
        catalogo = {4.0: 10615, 8.0: 10609}
        tipos = {10615: "Impoconsumo", 10609: "Impoconsumo"}
        for pct, tax_id, valor in ((4.0, 10615, 499.0), (8.0, 10609, 2518.52)):
            linea = _Linea(
                taxes=[{"esquema": "04", "porcentaje": pct, "valor": valor, "tax_id": tax_id}]
            )
            ids, importe, _ = impuestos_de_la_linea(linea, catalogo, tipos)
            assert (ids, importe) == ([tax_id], valor)

    def test_los_decimales_no_se_arrastran_en_coma_flotante(self):
        """0,1 + 0,2 en binario no es 0,3. El importe se redondea a dos decimales."""
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 0.1, "tax_id": 20921},
                {"esquema": "04", "porcentaje": 4.0, "valor": 0.2, "tax_id": 10615},
            ]
        )
        assert impuestos_de_la_linea(linea, CATALOGO_COMPLETO, TIPOS_COMPLETO)[1] == 0.3
