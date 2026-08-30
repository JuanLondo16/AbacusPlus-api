"""Solo ReteICA y ReteIVA llegan a SIIGO en una factura de compra.

`POST /v1/purchases` expone `retentions` en la raíz, documentado como «Array con los id de
los impuestos tipo ReteICA, ReteIVA». Se intentó además enviar la Retefuente en
`items[].taxes`, porque el enum `TaxType` la incluye y la única prohibición escrita para los
ítems es «Si envías un reteIVA o reteICA en los items de factura»: por eliminación parecía su
sitio.

La API desmintió esa deducción. Con la factura 941457814 se comprobaron los dos caminos:

    retentions      → invalid_array: "The array id has invalid values"
    items[0].taxes  → invalid_array: "The array taxes has invalid values"

Enviando Retefuente 1 %, Autorretención 1,10 % e Impoconsumo 8 %. Con los dos sitios
cerrados, la conclusión es que el endpoint NO recibe esas retenciones: SIIGO las practica por
su propia configuración. `items[].taxes` sí acepta el IVA —así se contabilizan todos los
documentos hoy—, de modo que admite impuestos de línea, no retenciones.

Estas pruebas fijan ese límite para que nadie vuelva a deducirlo del blueprint: la
documentación sugiere lo contrario, y el ambiente real manda.
"""

from types import SimpleNamespace

from app.application.use_cases.account_document import AccountDocumentUseCase

#: (id, tipo, porcentaje) tal como quedan tras sincronizar el catálogo con SIIGO.
_CATALOGO = {
    10596: ("retefuente", 11.0),
    10614: ("retefuente", 1.0),
    10598: ("retefuente", 6.0),
    10604: ("reteica", 8.66),
    10608: ("reteiva", 15.0),
    10609: ("impoconsumo", 8.0),
    20922: ("autorretencion", 1.1),
}


class _Repo:
    def __init__(self, catalogo=_CATALOGO):
        self.db = SimpleNamespace(execute=self._execute)
        self._catalogo = catalogo

    def _execute(self, _sentencia, parametros=None):
        ids = (parametros or {}).get("ids", [])
        filas = [(i, *self._catalogo[i]) for i in ids if i in self._catalogo]
        # `_tipos_de_impuesto` pide (id, type) y `_retenciones_del_catalogo` (id, type, pct).
        return SimpleNamespace(fetchall=lambda: filas)


def _caso() -> AccountDocumentUseCase:
    caso = AccountDocumentUseCase.__new__(AccountDocumentUseCase)
    caso.document_repo = _Repo()
    return caso


def _doc(*retenciones) -> SimpleNamespace:
    """`retenciones` son tuplas (tax_id, valor, base)."""
    return SimpleNamespace(
        taxes=[
            SimpleNamespace(tax_id=tid, value=valor, taxable_base=base)
            for tid, valor, base in retenciones
        ]
    )


_SUBTOTAL = 132773.11


class TestDestinoDeCadaRetencion:
    def test_1_documento_sin_retenciones(self):
        caso = _caso()
        doc = _doc()

        assert caso._retention_ids(doc) == []
        assert caso._retenciones_por_item(doc, _SUBTOTAL) == []

    def test_2_la_retefuente_no_llega_a_siigo(self):
        """Rechazada en los dos sitios: `retentions` y `items[].taxes`."""
        caso = _caso()
        doc = _doc((10596, 14605.04, _SUBTOTAL))

        assert caso._retention_ids(doc) == []
        assert caso._retenciones_por_item(doc, _SUBTOTAL) == []

    def test_3_solo_reteica_viaja_en_el_documento(self):
        caso = _caso()
        doc = _doc((10604, 846.85, _SUBTOTAL))

        assert caso._retention_ids(doc) == [10604]
        assert caso._retenciones_por_item(doc, _SUBTOTAL) == []

    def test_4_solo_reteiva_viaja_en_el_documento(self):
        caso = _caso()
        doc = _doc((10608, 3150.81, 21005.38))

        assert caso._retention_ids(doc) == [10608]
        assert caso._retenciones_por_item(doc, _SUBTOTAL) == []

    def test_5_de_varias_solo_pasan_las_dos_admitidas(self):
        """Es el caso que importa: las admitidas no se pierden por culpa de las otras."""
        caso = _caso()
        doc = _doc(
            (10608, 3150.81, 21005.38),
            (10604, 846.85, _SUBTOTAL),
            (10596, 14605.04, _SUBTOTAL),
        )

        assert sorted(caso._retention_ids(doc)) == [10604, 10608]
        assert caso._retenciones_por_item(doc, _SUBTOTAL) == []

    def test_una_retencion_en_cero_no_se_practico(self):
        caso = _caso()
        doc = _doc((10608, 0.0, 21005.38))

        assert caso._retention_ids(doc) == []

    def test_no_se_duplica_la_misma_retencion(self):
        caso = _caso()
        doc = _doc((10608, 3150.81, 21005.38), (10608, 3150.81, 21005.38))

        assert caso._retention_ids(doc) == [10608]


class TestAplicacionEnLosItems:
    def _items(self, *tax_ids_por_item):
        return [
            {"type": "Account", "code": "51401590", "quantity": 1.0, "price": 100.0,
             **({"tax_ids": list(ids)} if ids else {})}
            for ids in tax_ids_por_item
        ]

    def test_6_se_aplica_a_todas_las_lineas(self):
        caso = _caso()
        items = self._items([20921], [20921], [])

        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert items[0]["tax_ids"] == [20921, 10596]
        assert items[1]["tax_ids"] == [20921, 10596]
        assert items[2]["tax_ids"] == [10596]

    def test_7_un_item_sin_iva_recibe_solo_la_retencion(self):
        caso = _caso()
        items = self._items([])

        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert items[0]["tax_ids"] == [10596]

    def test_no_se_pierde_el_iva_de_la_linea(self):
        """Se suma a lo que ya lleva; nunca lo sustituye."""
        caso = _caso()
        items = self._items([20921])

        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert 20921 in items[0]["tax_ids"]

    def test_no_se_repite_el_mismo_impuesto_en_un_item(self):
        """SIIGO rechaza «un mismo tipo de impuesto más de una vez»."""
        caso = _caso()
        items = self._items([10596])

        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert items[0]["tax_ids"] == [10596]

    def test_se_respeta_el_tope_de_tres_impuestos_por_item(self):
        """«puedes enviar hasta 3 impuestos»: superarlo tumba el documento entero."""
        caso = _caso()
        items = self._items([20921, 10609, 14165])

        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert len(items[0]["tax_ids"]) == 3
        assert 10596 not in items[0]["tax_ids"]

    def test_sin_retenciones_los_items_no_se_tocan(self):
        caso = _caso()
        items = self._items([20921])

        caso._aplicar_retenciones_a_los_items(items, [])

        assert items[0]["tax_ids"] == [20921]

    def test_es_idempotente(self):
        """Un reintento no puede acumular la misma retención dos veces."""
        caso = _caso()
        items = self._items([20921])

        caso._aplicar_retenciones_a_los_items(items, [10596])
        caso._aplicar_retenciones_a_los_items(items, [10596])

        assert items[0]["tax_ids"] == [20921, 10596]


class TestEfectoEnElPago:
    """SIIGO resta lo retenido del total que espera en `payments`."""

    def test_8_la_retefuente_se_calcula_sobre_el_subtotal(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10596], 132773.11, 25226.89) == round(
            132773.11 * 11 / 100, 2
        )

    def test_la_reteica_sigue_siendo_por_mil(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10604], 42804.00, 8096.00) == 370.68

    def test_la_reteiva_parte_del_iva(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([10608], 132773.11, 21005.38) == round(
            21005.38 * 15 / 100, 2
        )

    def test_9_el_redondeo_es_a_dos_decimales(self):
        caso = _caso()
        valor = caso._retencion_que_aplicara_siigo([10596], 1234.567, 0.0)

        assert valor == round(valor, 2)

    def test_sin_retenciones_no_hay_descuento(self):
        caso = _caso()

        assert caso._retencion_que_aplicara_siigo([], 132773.11, 25226.89) == 0.0


class TestLaLineaDelImpuestoAlConsumoNoAlteraLaBase:
    """La línea del impuesto al consumo la añade Abacus, no la factura.

    Ocurrió con el documento E6038096228: sus líneas suman 58.431,09 —que es la base de la
    Retefuente 6 % que registró el contador— y la línea de ajuste del impuesto al consumo
    sumaba 116,86 más. La comprobación de la base se hacía contra ese total inflado, no
    coincidía, y la retención se descartaba en silencio: SIIGO contabilizó el documento sin
    practicar ninguna.

    La base a contrastar es la de las líneas REALES, y la línea de ajuste queda fuera del
    reparto: es un impuesto, no una base gravable.
    """

    _SUBTOTAL_REAL = 58431.09
    _AJUSTE_INC = 116.86

    def test_la_base_se_contrasta_contra_el_subtotal_real(self):
        """La comprobación de base sigue viva aunque hoy no viaje ninguna retención de línea.

        Es el mecanismo el que se conserva: si SIIGO habilita algún tipo por ítem, la base
        debe seguir contrastándose contra las líneas reales y no contra el total inflado por
        la línea de ajuste del impuesto al consumo.
        """
        caso = _caso()
        doc = _doc((10614, 3505.87, self._SUBTOTAL_REAL))

        # Con la tupla vacía no se envía ninguna, que es el estado comprobado contra SIIGO.
        assert caso._retenciones_por_item(doc, self._SUBTOTAL_REAL) == []

    def test_con_el_subtotal_inflado_se_habria_descartado(self):
        """Reproduce el fallo: comparar contra el total con el ajuste la deja fuera."""
        caso = _caso()
        doc = _doc((10614, 3505.87, self._SUBTOTAL_REAL))
        inflado = self._SUBTOTAL_REAL + self._AJUSTE_INC

        assert caso._retenciones_por_item(doc, inflado) == []

    def test_la_linea_de_ajuste_no_recibe_retenciones(self):
        """Se le aplica solo a las líneas reales, que es lo que recorta quien llama."""
        caso = _caso()
        items = [
            {"type": "Account", "code": "51353501", "quantity": 1.0,
             "price": 58431.09, "tax_ids": [20921]},
            {"type": "Account", "code": "51159509", "quantity": 1.0,
             "price": 116.86, "description": "Impuesto al consumo"},
        ]

        caso._aplicar_retenciones_a_los_items(items[:1], [10614])

        assert items[0]["tax_ids"] == [20921, 10614]
        assert "tax_ids" not in items[1], "el ajuste no es base de retención"


class TestLosTiposQueSiigoRechaza:
    """Retefuente, Autorretención e Impoconsumo no llegan por la API de compras.

    Los tres se enviaron juntos en `items[0].taxes` de la factura 941457814 y SIIGO respondió
    `invalid_array: "The array taxes has invalid values"`. No se envían, y queda registrado
    para que el contador sepa que no se practicaron.
    """

    _SUBTOTAL_DOC = 58431.11

    def test_ninguno_de_los_tres_viaja(self):
        caso = _caso()
        for tax_id in (10598, 20922, 10609):
            doc = _doc((tax_id, 1000.0, self._SUBTOTAL_DOC))

            assert caso._retenciones_por_item(doc, self._SUBTOTAL_DOC) == []
            assert caso._retention_ids(doc) == []

    def test_el_documento_real_no_envia_ninguna(self):
        """E6038096228: las tres registradas, ninguna admitida por la API."""
        caso = _caso()
        doc = _doc(
            (10598, 3505.87, self._SUBTOTAL_DOC),
            (20922, 642.74, self._SUBTOTAL_DOC),
            (10609, 4674.49, self._SUBTOTAL_DOC),
        )

        assert caso._retenciones_por_item(doc, self._SUBTOTAL_DOC) == []
        assert caso._retention_ids(doc) == []

    def test_el_mecanismo_por_item_sigue_disponible(self):
        """La tupla está vacía, no borrada: declarar un tipo lo reactiva."""
        assert AccountDocumentUseCase.TIPOS_DE_RETENCION_POR_ITEM == ()
