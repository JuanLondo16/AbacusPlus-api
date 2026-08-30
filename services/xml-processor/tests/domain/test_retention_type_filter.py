"""Solo ReteICA y ReteIVA viajan en `retentions` de una factura de compra.

La tabla de `POST /v1/purchases` lo dice literalmente: «Array con los id de los impuestos
tipo ReteICA, ReteIVA». La retención en la fuente no entra ahí: SIIGO la aplica por la
configuración del tercero. Mandarla produce `invalid_array: The array id has invalid values`
sobre `retentions[0].id`, y eso rechaza la factura completa.

Ocurrió contra el ambiente real con el documento G3Z8211963: una Retefuente 1% (id 10614,
ya correcto tras la reidentificación del catálogo) tumbaba el envío.
"""

from types import SimpleNamespace

from app.application.use_cases.account_document import AccountDocumentUseCase


class _Catalogo:
    """Sustituto del repositorio: solo aporta el `db` que consulta los tipos."""

    def __init__(self, tipos: dict, revienta: bool = False):
        self.db = SimpleNamespace(execute=self._execute)
        self._tipos = tipos
        self._revienta = revienta

    def _execute(self, _sentencia, parametros):
        if self._revienta:
            raise RuntimeError("catálogo no disponible")
        ids = parametros["ids"]
        filas = [(i, self._tipos[i]) for i in ids if i in self._tipos]
        return SimpleNamespace(fetchall=lambda: filas)


def _caso(tipos: dict, revienta: bool = False) -> AccountDocumentUseCase:
    caso = AccountDocumentUseCase.__new__(AccountDocumentUseCase)
    caso.document_repo = _Catalogo(tipos, revienta)
    return caso


def _documento(*pares) -> SimpleNamespace:
    return SimpleNamespace(
        taxes=[SimpleNamespace(tax_id=tid, value=valor) for tid, valor in pares]
    )


class TestFiltroPorTipo:
    def test_la_retefuente_no_viaja_en_retentions(self):
        """El caso real: Retefuente 1% tumbaba el documento G3Z8211963."""
        caso = _caso({10614: "Retefuente"})

        assert caso._retention_ids(_documento((10614, 408.0))) == []

    def test_reteiva_y_reteica_si_viajan(self):
        caso = _caso({10608: "ReteIVA", 10601: "ReteICA"})

        resultado = caso._retention_ids(_documento((10608, 641.11), (10601, 50.0)))

        assert resultado == [10608, 10601]

    def test_el_impoconsumo_tampoco_es_una_retencion(self):
        caso = _caso({10609: "Impoconsumo"})

        assert caso._retention_ids(_documento((10609, 8964.21))) == []

    def test_de_una_mezcla_solo_pasan_los_admitidos(self):
        """El documento 28 real: Impoconsumo + Retefuente. Ninguno debe pasar."""
        caso = _caso({10609: "Impoconsumo", 10614: "Retefuente", 10608: "ReteIVA"})

        resultado = caso._retention_ids(
            _documento((10609, 8964.21), (10614, 1120.53), (10608, 641.11))
        )

        assert resultado == [10608]

    def test_el_tipo_se_compara_sin_distinguir_mayusculas(self):
        caso = _caso({10608: "reteiva", 10601: "RETEICA"})

        assert caso._retention_ids(_documento((10608, 1), (10601, 2))) == [10608, 10601]

    def test_una_retencion_en_cero_no_se_practico(self):
        caso = _caso({10608: "ReteIVA"})

        assert caso._retention_ids(_documento((10608, 0))) == []

    def test_no_se_repiten_los_identificadores(self):
        caso = _caso({10608: "ReteIVA"})

        assert caso._retention_ids(_documento((10608, 10), (10608, 20))) == [10608]

    def test_un_documento_sin_retenciones_no_consulta_nada(self):
        """Las retenciones son opcionales: la mayoría de documentos no lleva ninguna."""
        caso = _caso({}, revienta=True)

        assert caso._retention_ids(_documento()) == []

    def test_si_el_catalogo_no_responde_no_se_descarta_en_silencio(self):
        """Un fallo de infraestructura no debe cambiar qué se contabiliza."""
        caso = _caso({}, revienta=True)

        assert caso._retention_ids(_documento((10608, 641.11))) == [10608]

    def test_un_impuesto_ausente_del_catalogo_no_viaja(self):
        """Sin tipo conocido no hay forma de afirmar que SIIGO lo acepta."""
        caso = _caso({10608: "ReteIVA"})

        assert caso._retention_ids(_documento((99999, 100.0))) == []
