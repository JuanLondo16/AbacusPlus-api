"""Las reglas que SIIGO impone a `items[].taxes`, aplicadas antes de enviar.

El blueprint las publica como causas del error `invalid_array`:

    - Si envías más de la cantidad de impuestos permitidos, puedes enviar hasta 3 impuestos.
    - Si envías Iva y Ad Valorem en el mismo producto de una factura.
    - Si envías un mismo tipo de impuesto más de una vez.
    - Si envías un reteIVA o reteICA en los items de factura.

Se comprueban aquí y no se dejan al servidor porque **un rechazo por este motivo tumba el
documento entero**, no la línea. Y porque el coste de un rechazo no es solo el reintento: la
cuenta de SIIGO se bloquea si la proporción de errores supera el 80 % durante siete días.

La comprobación que faltaba es la del **tipo**. El código deduplicaba por identificador, y el
catálogo del cliente tiene cinco impuestos distintos al 19 %: dos ids diferentes del tipo IVA
en la misma línea pasaban el filtro local y eran rechazados por SIIGO.
"""

from app.domain.services.siigo_item_taxes import MAX_IMPUESTOS_POR_ITEM, componer_impuestos_de_linea


def _c(id_, tipo):
    """Un candidato a impuesto de línea: su id de SIIGO y su tipo."""
    return (id_, tipo)


class TestLimiteDeTresImpuestos:
    def test_admite_hasta_tres(self):
        ids, avisos = componer_impuestos_de_linea(
            [_c(1, "IVA"), _c(2, "Impoconsumo"), _c(3, "INC Bolsas")]
        )
        assert ids == [1, 2, 3]
        assert avisos == []

    def test_descarta_el_cuarto_y_lo_avisa(self):
        """No se envía una línea que SIIGO va a rechazar, y el descarte queda dicho."""
        ids, avisos = componer_impuestos_de_linea(
            [_c(1, "IVA"), _c(2, "Impoconsumo"), _c(3, "INC Bolsas"), _c(4, "Otro")]
        )
        assert ids == [1, 2, 3]
        assert len(ids) <= MAX_IMPUESTOS_POR_ITEM
        assert any("4" in a for a in avisos)


class TestUnSoloImpuestoPorTipo:
    def test_descarta_el_segundo_impuesto_del_mismo_tipo(self):
        """Dos IVA distintos en la misma línea son un rechazo seguro.

        Es el caso real del catálogo del cliente: «IVA 19%» e «IVA 19%.» tienen ids
        diferentes y el mismo tipo. Deduplicar por id los dejaba pasar a los dos.
        """
        ids, avisos = componer_impuestos_de_linea([_c(101, "IVA"), _c(950, "IVA")])
        assert ids == [101]
        assert any("tipo" in a.lower() for a in avisos)

    def test_compara_el_tipo_sin_distinguir_mayusculas(self):
        """El catálogo escribe el mismo tipo de varias formas."""
        ids, _ = componer_impuestos_de_linea([_c(101, "IVA"), _c(950, "iva")])
        assert ids == [101]

    def test_el_mismo_id_repetido_solo_entra_una_vez(self):
        ids, _ = componer_impuestos_de_linea([_c(101, "IVA"), _c(101, "IVA")])
        assert ids == [101]


class TestIvaYAdValoremSonIncompatibles:
    def test_no_viajan_juntos_en_la_misma_linea(self):
        """El blueprint lo prohíbe expresamente."""
        ids, avisos = componer_impuestos_de_linea([_c(101, "IVA"), _c(700, "AdValorem")])
        assert ids == [101]
        assert any("advalorem" in a.lower() for a in avisos)

    def test_el_iva_manda_sobre_el_advalorem_sin_importar_el_orden(self):
        """Llegue como llegue la línea, se conserva el IVA: es el impuesto que la DIAN
        declara en la inmensa mayoría de los documentos."""
        ids, _ = componer_impuestos_de_linea([_c(700, "AdValorem"), _c(101, "IVA")])
        assert ids == [101]

    def test_el_advalorem_solo_si_va_sin_iva(self):
        ids, avisos = componer_impuestos_de_linea([_c(700, "AdValorem")])
        assert ids == [700]
        assert avisos == []


class TestLasRetencionesNoVanEnLaLinea:
    def test_descarta_reteiva_y_reteica(self):
        """El blueprint lo prohíbe, y ponerlos ahí los restaría en vez de sumarlos."""
        ids, avisos = componer_impuestos_de_linea(
            [_c(101, "IVA"), _c(500, "ReteIVA"), _c(600, "ReteICA")]
        )
        assert ids == [101]
        assert len(avisos) >= 1

    def test_descarta_retefuente(self):
        """Comprobado contra el ambiente real: `items[0].taxes → invalid_array`."""
        ids, _ = componer_impuestos_de_linea([_c(101, "IVA"), _c(303, "Retefuente")])
        assert ids == [101]

    def test_descarta_autorretencion(self):
        """En una compra no existe: `self_withholding` solo está en el comprobante de venta."""
        ids, _ = componer_impuestos_de_linea([_c(101, "IVA"), _c(404, "Autorretencion")])
        assert ids == [101]


class TestCasosVacios:
    def test_sin_candidatos_no_hay_impuestos(self):
        assert componer_impuestos_de_linea([]) == ([], [])

    def test_ignora_candidatos_sin_identificador(self):
        ids, _ = componer_impuestos_de_linea([_c(None, "IVA"), _c(101, "IVA")])
        assert ids == [101]

    def test_conserva_el_orden_de_llegada(self):
        """El primero de la línea es el que la DIAN declaró primero; se respeta."""
        ids, _ = componer_impuestos_de_linea([_c(10, "Impoconsumo"), _c(101, "IVA")])
        assert ids == [10, 101]
