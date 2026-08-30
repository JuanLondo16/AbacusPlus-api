"""Los ítems llevan su impuesto y el pago cuadra con lo que SIIGO calcula.

SIIGO calcula el total de la compra sumando las bases de los ítems más los impuestos que
esos ítems declaran, y exige que el pago coincida exactamente:
`The total payments must be equal to the total purchase`.

El XML de la DIAN trae el impuesto de cada línea como un porcentaje, no como un id. Sin
traducirlo, los ítems viajaban sin impuestos y SIIGO calculaba solo las bases, mientras el
pago se enviaba con el total de la factura. El descuadre rechazaba el documento entero.

Las cifras son las de la factura real BEC514712399 (Colombia Telecomunicaciones), cuyo
rechazo decía literalmente `The total purchase calculated is 102926.32` — la suma de las
bases, 93326.32 + 9600.
"""

from types import SimpleNamespace

from app.application.use_cases.account_document import AccountDocumentUseCase

#: El catálogo real, ya reidentificado con los ids de SIIGO.
_CATALOGO = [
    (10594, "IVA", 19.0),
    (20880, "IVA", 19.0),      # «Iva servicios 19%», id mayor: no debe ganar
    (20921, "IVA", 19.0),      # «IVA 19%.», id mayor: no debe ganar
    (10595, "IVA", 5.0),
    (14165, "IVA", 0.0),
    (10609, "Impoconsumo", 8.0),
    (10608, "ReteIVA", 15.0),
]


class _Catalogo:
    def __init__(self, filas=_CATALOGO, revienta=False):
        self.db = SimpleNamespace(execute=self._execute)
        self._filas = filas
        self._revienta = revienta

    def _execute(self, *_args, **_kwargs):
        if self._revienta:
            raise RuntimeError("catálogo no disponible")
        return SimpleNamespace(fetchall=lambda: list(self._filas))


def _caso(**kwargs) -> AccountDocumentUseCase:
    caso = AccountDocumentUseCase.__new__(AccountDocumentUseCase)
    caso.document_repo = _Catalogo(**kwargs)
    return caso


def _linea(subtotal, tax_type, tax_id=None, cantidad=1.0):
    return SimpleNamespace(
        quantity=cantidad,
        price=subtotal / cantidad,
        tax_type=tax_type,
        tax_id=tax_id,
        description="linea",
        code="51353501",
        type="Account",
    )


class TestTraduccionDelPorcentaje:
    def test_el_19_por_ciento_toma_el_iva_canonico(self):
        """Cinco impuestos comparten el 19%: debe ganar el de menor id."""
        caso = _caso()

        assert caso._catalogo_de_impuestos_por_porcentaje()[19.0] == 10594

    def test_el_8_por_ciento_cae_en_impoconsumo(self):
        """No hay ningún IVA al 8%; el catálogo solo tiene Impoconsumo."""
        caso = _caso()

        assert caso._catalogo_de_impuestos_por_porcentaje()[8.0] == 10609

    def test_se_prefiere_el_iva_aunque_otro_tipo_tenga_id_menor(self):
        caso = _caso(filas=[(100, "Impoconsumo", 19.0), (10594, "IVA", 19.0)])

        assert caso._catalogo_de_impuestos_por_porcentaje()[19.0] == 10594


class TestImpuestoDeLaLinea:
    def test_el_porcentaje_se_traduce_a_id(self):
        caso = _caso()
        catalogo = caso._catalogo_de_impuestos_por_porcentaje()

        assert caso._impuesto_de_la_linea(_linea(1000, "19.00"), catalogo) == (10594, 19.0)

    def test_el_tax_id_elegido_por_el_contador_manda(self):
        caso = _caso()
        catalogo = caso._catalogo_de_impuestos_por_porcentaje()

        assert caso._impuesto_de_la_linea(
            _linea(1000, "19.00", tax_id=20880), catalogo
        ) == (20880, 19.0)

    def test_un_cero_no_lleva_impuesto(self):
        """Un «IVA 0%» explícito no cambia el total y añade una referencia que puede fallar."""
        caso = _caso()
        catalogo = caso._catalogo_de_impuestos_por_porcentaje()

        assert caso._impuesto_de_la_linea(_linea(1000, "0"), catalogo) == (None, 0.0)
        assert caso._impuesto_de_la_linea(_linea(1000, "0.00"), catalogo) == (None, 0.0)

    def test_un_porcentaje_sin_catalogo_no_inventa_un_id(self):
        caso = _caso()
        catalogo = caso._catalogo_de_impuestos_por_porcentaje()

        assert caso._impuesto_de_la_linea(_linea(1000, "33.00"), catalogo) == (None, 0.0)

    def test_una_linea_sin_tax_type_no_revienta(self):
        """Los documentos antiguos y los tests construyen líneas sin ese campo."""
        caso = _caso()
        linea = SimpleNamespace(quantity=1.0, price=100.0, tax_id=None, description="x")

        assert caso._impuesto_de_la_linea(linea, {}) == (None, 0.0)


class TestElTotalQueEsperaSiigo:
    """La aritmética exacta de la factura BEC514712399."""

    def _total(self, caso, lineas) -> float:
        catalogo = caso._catalogo_de_impuestos_por_porcentaje()
        total = 0.0
        for linea in lineas:
            _, porcentaje = caso._impuesto_de_la_linea(linea, catalogo)
            base = round(linea.quantity * linea.price, 2)
            total += base + round(base * porcentaje / 100.0, 2)
        return round(total, 2)

    def test_sin_impuestos_el_total_es_solo_la_base(self):
        """Lo que SIIGO calculaba antes de la corrección: 102926.32."""
        caso = _caso()
        lineas = [_linea(93326.32, "0"), _linea(9600.0, "0")]

        assert self._total(caso, lineas) == 102926.32

    def test_con_el_iva_de_las_lineas_el_total_es_el_de_la_factura(self):
        caso = _caso()
        lineas = [_linea(93326.32, "19.00"), _linea(9600.0, "19.00")]

        assert self._total(caso, lineas) == 122482.32

    def test_una_linea_al_cinco_por_ciento(self):
        caso = _caso()

        assert self._total(caso, [_linea(1000.0, "5.00")]) == 1050.0

    def test_varias_cantidades_multiplican_la_base(self):
        caso = _caso()
        linea = _linea(3697.48, "19.00", cantidad=2.0)

        assert self._total(caso, [linea]) == round(3697.48 * 1.19, 2)


class TestPrecioBase:
    """SIIGO calcula la base como `quantity * price`: el precio decide qué se contabiliza.

    Estos son casos reales del cliente en los que `detail.price` NO es la base gravable.
    """

    def test_un_precio_con_iva_incluido_se_convierte_a_base(self):
        """«DONA RELL CHOC»: 2 x 3500 = 7000, pero la base gravable es 5882."""
        caso = _caso()
        linea = SimpleNamespace(quantity=2.0, price=3500.0, subtotal=5882.0)

        assert round(caso._precio_base(linea, 2.0) * 2, 2) == 5882.0

    def test_una_linea_con_descuento_usa_la_base_neta(self):
        """«SERVICIO DE ASEO»: 4 x 129579.98 = 518319.92 frente a 497587.12 reales."""
        caso = _caso()
        linea = SimpleNamespace(quantity=4.0, price=129579.98, subtotal=497587.12)

        assert round(caso._precio_base(linea, 4.0) * 4, 2) == 497587.12

    def test_cuando_ya_son_coherentes_no_cambia_nada(self):
        """La factura de Telefónica: cantidad 1 y el precio ya es la base."""
        caso = _caso()
        linea = SimpleNamespace(quantity=1.0, price=93326.32, subtotal=93326.32)

        assert caso._precio_base(linea, 1.0) == 93326.32

    def test_sin_subtotal_se_conserva_el_precio(self):
        """No se altera el comportamiento de los documentos que no traen ese dato."""
        caso = _caso()
        linea = SimpleNamespace(quantity=2.0, price=1500.0, subtotal=None)

        assert caso._precio_base(linea, 2.0) == 1500.0

    def test_una_cantidad_de_cero_no_divide_por_cero(self):
        caso = _caso()
        linea = SimpleNamespace(quantity=0.0, price=1500.0, subtotal=3000.0)

        assert caso._precio_base(linea, 0.0) == 1500.0

    def test_la_base_reconstruida_reproduce_el_total_de_la_linea(self):
        """Con la base correcta, base + IVA vuelve a dar el total que facturó el proveedor."""
        caso = _caso()
        linea = SimpleNamespace(quantity=1.0, price=139000.0, subtotal=50966.0)

        base = round(caso._precio_base(linea, 1.0) * 1.0, 2)
        assert round(base + round(base * 0.19, 2), 2) == 60649.54
