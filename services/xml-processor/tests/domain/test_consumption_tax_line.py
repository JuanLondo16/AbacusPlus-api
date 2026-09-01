"""El impuesto al consumo llega a nivel de documento y debe acabar en el asiento.

La DIAN lo reporta en el `TaxTotal` del documento, no en las líneas. En las facturas «BEC»
no existe ninguna línea que lo represente, así que contabilizar solo las líneas dejaba la
deuda con el proveedor por debajo de lo facturado: entre 192 y 506 pesos por documento, en
los doce documentos de telecomunicaciones del cliente.

`documents.total_taxes` sí lo incluye. La diferencia entre ese campo y la suma del IVA de
las líneas es exactamente el impuesto al consumo, y eso es lo que permite reconocerlo y
distinguirlo del redondeo a peso de los totales de la DIAN.
"""

from types import SimpleNamespace

from app.application.use_cases.account_document import AccountDocumentUseCase


def _caso() -> AccountDocumentUseCase:
    return AccountDocumentUseCase.__new__(AccountDocumentUseCase)


def _linea(subtotal, tax_value, descripcion="linea", code="51353501", price=None):
    return SimpleNamespace(
        quantity=1.0,
        price=price if price is not None else subtotal,
        subtotal=subtotal,
        tax_value=tax_value,
        description=descripcion,
        code=code,
        type="Account",
    )


class TestDeteccionDelImpuestoAlConsumo:
    def test_la_factura_bec_declara_impuestos_que_ninguna_linea_recoge(self):
        """BEC514712399: total_taxes 19940 frente a 19556 de IVA en líneas."""
        caso = _caso()
        doc = SimpleNamespace(total_taxes=19940.0)
        lineas = [_linea(93326.32, 17732.0), _linea(9600.0, 1824.0)]

        assert caso._impuestos_no_desglosados(doc, lineas) == 384.0

    def test_la_factura_bev_ya_trae_el_impuesto_en_una_linea(self):
        """BEV24837203: total_taxes 8288 frente a 8096 de IVA."""
        caso = _caso()
        doc = SimpleNamespace(total_taxes=8288.0)
        lineas = [_linea(40089.47, 7617.0), _linea(2521.05, 479.0)]

        assert caso._impuestos_no_desglosados(doc, lineas) == 192.0

    def test_un_documento_sin_impuestos_ocultos_no_declara_ninguno(self):
        caso = _caso()
        doc = SimpleNamespace(total_taxes=1900.0)

        assert caso._impuestos_no_desglosados(doc, [_linea(10000.0, 1900.0)]) == 0.0

    def test_un_total_de_impuestos_ausente_no_revienta(self):
        caso = _caso()

        assert caso._impuestos_no_desglosados(SimpleNamespace(), [_linea(100.0, 19.0)]) == 0.0


class TestCuentaDelImpuestoAlConsumo:
    def test_se_toma_la_cuenta_que_uso_el_proveedor(self):
        """En las «BEV» el impuesto sí viene como línea: su cuenta es la mejor referencia."""
        caso = _caso()
        lineas = [
            _linea(40089.47, 7617.0),
            _linea(0, 0, descripcion="Impuesto al consumo de voz 4%", code="51159509", price=192.0),
        ]

        assert caso._cuenta_de_impuesto_al_consumo(lineas) == "51159509"

    def test_sin_esa_linea_no_se_inventa_una_cuenta(self):
        """Las «BEC» no la traen: quien decide es la plantilla o el valor por defecto."""
        caso = _caso()

        assert caso._cuenta_de_impuesto_al_consumo([_linea(93326.32, 17732.0)]) is None

    def test_una_linea_normal_no_se_confunde_con_el_impuesto(self):
        caso = _caso()
        lineas = [_linea(1000.0, 190.0, descripcion="Plan Pospago consumo de datos")]

        assert caso._cuenta_de_impuesto_al_consumo(lineas) is None


class TestUmbralDelAjuste:
    def test_el_umbral_ignora_los_centimos(self):
        """Los totales de la DIAN vienen redondeados a peso: por debajo es redondeo."""
        assert AccountDocumentUseCase.UMBRAL_DE_AJUSTE == 1.0

    def test_hay_una_cuenta_por_defecto_documentada(self):
        assert AccountDocumentUseCase.CUENTA_IMPUESTO_AL_CONSUMO == "51159509"
