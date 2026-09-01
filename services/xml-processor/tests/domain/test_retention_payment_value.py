"""En una factura de compra el pago es el NETO de retenciones.

SIIGO valida `payments` contra el total que él calcula, y en compras ese total ya viene
descontado de lo retenido. Enviando el bruto respondía:

    invalid_total_payments — "The total payments must be equal to the total purchase.
    The total purchase calculated is 50529.32"

Las cifras de estas pruebas son las del documento real BEV24837203:

    bases   40089.47 + 2521.05 + 192.00 + 1.48 = 42804.00
    IVA     (40089.47 + 2521.05) * 19%         =  8096.00
    total                                       = 50900.00
    ReteICA 42804.00 * 8.66 / 1000              =  -370.68
    neto                                        = 50529.32   <- lo que SIIGO esperaba

La tarifa de ReteICA se maneja por mil, no por ciento. Se comprobó contra el ambiente real
y coincide con el aviso que la propia interfaz ya mostraba: el catálogo de impuestos trae
«11.04» donde la tabla de ReteICA trae «1.104».
"""

from types import SimpleNamespace

import pytest
from app.application.use_cases.account_document import AccountDocumentUseCase

#: (id, tipo, porcentaje) tal y como están en el catálogo tras la sincronización con SIIGO.
_CATALOGO = {
    10604: ("reteica", 8.66),
    10608: ("reteiva", 15.0),
    10614: ("retefuente", 1.0),
}


class _Repo:
    def __init__(self, catalogo=_CATALOGO, revienta=False):
        self.db = SimpleNamespace(execute=self._execute)
        self._catalogo = catalogo
        self._revienta = revienta

    def _execute(self, _sentencia, parametros=None):
        if self._revienta:
            raise RuntimeError("catálogo no disponible")
        ids = (parametros or {}).get("ids", [])
        filas = [
            (i, self._catalogo[i][0], self._catalogo[i][1]) for i in ids if i in self._catalogo
        ]
        return SimpleNamespace(fetchall=lambda: filas)


def _caso(**kwargs) -> AccountDocumentUseCase:
    caso = AccountDocumentUseCase.__new__(AccountDocumentUseCase)
    caso.document_repo = _Repo(**kwargs)
    return caso


#: Las cifras del documento real.
_SUBTOTAL = 42804.00
_IVA = 8096.00
_TOTAL = 50900.00


class TestConRetenciones:
    def test_la_reteica_se_calcula_por_mil_sobre_el_subtotal(self):
        """El caso exacto que SIIGO rechazó: esperaba 370.68 retenidos."""
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10604], _SUBTOTAL, _IVA) == 370.68

    def test_el_pago_neto_coincide_con_el_total_que_calculo_siigo(self):
        caso = _caso()
        retenido = caso._retencion_que_aplicara_siigo([10604], _SUBTOTAL, _IVA)

        assert round(_TOTAL - retenido, 2) == 50529.32

    def test_la_reteiva_se_calcula_por_ciento_sobre_el_iva(self):
        """«ReteIVA: se aplica sobre el valor del IVA facturado» (doc. de SIIGO)."""
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10608], _SUBTOTAL, _IVA) == round(_IVA * 0.15, 2)

    def test_varias_retenciones_se_suman(self):
        caso = _caso()

        esperado = round(_SUBTOTAL * 8.66 / 1000, 2) + round(_IVA * 15.0 / 100, 2)
        assert caso._retencion_que_aplicara_siigo([10604, 10608], _SUBTOTAL, _IVA) == round(
            esperado, 2
        )

    def test_no_confundir_las_unidades_de_la_reteica(self):
        """8.66% serían 3706.80: diez veces de más. La unidad importa."""
        caso = _caso()
        retenido = caso._retencion_que_aplicara_siigo([10604], _SUBTOTAL, _IVA)

        assert retenido != round(_SUBTOTAL * 8.66 / 100, 2)
        assert retenido == pytest.approx(round(_SUBTOTAL * 8.66 / 100, 2) / 10, abs=0.01)


class TestSinRetenciones:
    def test_un_documento_sin_retenciones_no_descuenta_nada(self):
        """La mayoría de documentos no lleva ninguna: el pago sigue siendo el bruto."""
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([], _SUBTOTAL, _IVA) == 0.0

    def test_el_pago_sin_retenciones_es_el_total_de_los_items(self):
        caso = _caso()
        retenido = caso._retencion_que_aplicara_siigo([], _SUBTOTAL, _IVA)

        assert round(_TOTAL - retenido, 2) == _TOTAL


class TestCasosDefensivos:
    def test_la_retefuente_descuenta_sobre_el_subtotal(self):
        """Viaja en `items[].taxes`, pero SIIGO la resta igual del total esperado.

        Antes se descartaba —la API la rechaza en `retentions`— y por eso no afectaba al
        pago. Ahora va por ítem, que es su sitio, así que sí lo afecta: SIIGO la aplica a la
        base de cada línea y la suma de esas bases es el subtotal.
        """
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10614], _SUBTOTAL, _IVA) == round(
            _SUBTOTAL * 1.0 / 100, 2
        )

    def test_la_retefuente_no_se_calcula_sobre_el_iva(self):
        """Solo la ReteIVA parte del IVA facturado; el resto, del subtotal."""
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10614], _SUBTOTAL, _IVA) != round(
            _IVA * 1.0 / 100, 2
        )

    def test_una_retencion_ausente_del_catalogo_se_ignora(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([99999], _SUBTOTAL, _IVA) == 0.0

    def test_si_el_catalogo_falla_no_se_inventa_un_descuento(self):
        """Descontar a ciegas dejaría la deuda con el proveedor por debajo de lo debido."""
        caso = _caso(revienta=True)

        assert caso._retencion_que_aplicara_siigo([10604], _SUBTOTAL, _IVA) == 0.0

    def test_no_se_duplica_cuando_la_misma_retencion_llega_dos_veces(self):
        """`_retention_ids` ya deduplica; aquí se comprueba que el importe no se dobla."""
        caso = _caso()
        una = caso._retencion_que_aplicara_siigo([10604], _SUBTOTAL, _IVA)
        dos = caso._retencion_que_aplicara_siigo([10604, 10604], _SUBTOTAL, _IVA)

        assert dos == round(una * 2, 2), "si algún día llegan repetidas, se suman ambas"

    def test_una_base_en_cero_no_retiene(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10604], 0.0, 0.0) == 0.0
