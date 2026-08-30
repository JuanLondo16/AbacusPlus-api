"""Una sola forma de traducir el impuesto de una línea a su id del catálogo.

Por qué esto es un módulo de dominio y no un método privado
------------------------------------------------------------
La misma pregunta —«el XML dice 19 %, ¿qué impuesto del catálogo es?»— se respondía en dos
sitios y con reglas distintas:

- `process_xml._match_tax`, al guardar el documento, comparaba primero por **nombre** y luego
  por porcentaje, sin preferir ningún tipo ni desempatar.
- `account_document._catalogo_de_impuestos_por_porcentaje`, al construir el envío, indexaba
  por porcentaje prefiriendo el tipo IVA y quedándose con el id menor.

En la factura F78P21635 el resultado fue que las dos líneas quedaron con `tax_id` nulo en la
base mientras el envío sí viajó con `tax_ids: [10609]`. Dos capas decidiendo sobre lo mismo y
respondiendo distinto: la interfaz mostraba una cosa y a SIIGO iba otra, sin que el contador
tuviera forma de saber cuál mandaba.

Se unifica aquí, en una función pura, para que las dos capas no puedan volver a divergir.
"""

from app.domain.services.tax_resolution import indice_por_porcentaje, resolver_impuesto


def _tax(id_, tipo, porcentaje, nombre=None):
    return {
        "id": id_,
        "type": tipo,
        "percentage": porcentaje,
        "name": nombre or f"{tipo} {porcentaje}%",
    }


CATALOGO = [
    _tax(101, "IVA", 19.0, "IVA 19%"),
    _tax(950, "IVA", 19.0, "IVA 19%."),
    _tax(980, "Impoconsumo", 19.0, "Impoconsumo 19%"),
    _tax(10609, "Impoconsumo", 8.0, "Impoconsumo 8%"),
    _tax(202, "IVA", 5.0, "IVA 5%"),
    _tax(303, "ReteFuente", 4.0, "Retefuente 4%"),
]


class TestResolucionPorPorcentaje:
    def test_encuentra_el_impuesto_por_su_porcentaje(self):
        assert resolver_impuesto("5.00", CATALOGO) == 202

    def test_tolera_las_diferencias_de_formato_del_xml(self):
        """El XML emite «19.00» y el catálogo guarda 19; son el mismo impuesto."""
        assert resolver_impuesto("19.00", CATALOGO) == 101

    def test_prefiere_el_tipo_iva_cuando_varios_comparten_porcentaje(self):
        """Con IVA e Impoconsumo al 19 %, en una línea de venta manda el IVA."""
        assert resolver_impuesto("19", CATALOGO) == 101

    def test_desempata_por_el_id_menor_dentro_del_mismo_tipo(self):
        """El catálogo base de SIIGO tiene los ids bajos; las importaciones añaden gemelos.

        «IVA 19%» (101) e «IVA 19%.» (950) son la misma tarifa duplicada por combinar la
        sincronización con una importación de Excel. Elegir siempre el menor hace que la
        sugerencia sea repetible.
        """
        assert resolver_impuesto("19.00", CATALOGO) == 101

    def test_resuelve_el_ocho_por_ciento_al_impoconsumo(self):
        """Ningún IVA tiene 8 %: se recurre al otro tipo con ese porcentaje.

        Es el caso de la factura F78P21635, que no lleva IVA sino impuesto al consumo.
        """
        assert resolver_impuesto("8.00", CATALOGO) == 10609


class TestCasosQueNoDebenEnlazarse:
    def test_el_cero_por_ciento_no_lleva_impuesto(self):
        """Enviar un «IVA 0%» explícito no cambia el total y añade una referencia que puede
        fallar. Una línea exenta va sin impuesto."""
        assert resolver_impuesto("0.00", CATALOGO) is None
        assert resolver_impuesto("0", CATALOGO) is None

    def test_sin_porcentaje_no_hay_enlace(self):
        assert resolver_impuesto("", CATALOGO) is None
        assert resolver_impuesto(None, CATALOGO) is None

    def test_un_porcentaje_que_el_catalogo_no_tiene_devuelve_nada(self):
        """No se aproxima al más cercano: enlazar al impuesto equivocado es peor que no
        enlazar, porque el error queda registrado como una decisión."""
        assert resolver_impuesto("7.50", CATALOGO) is None

    def test_un_catalogo_vacio_devuelve_nada_sin_estallar(self):
        assert resolver_impuesto("19.00", []) is None
        assert resolver_impuesto("19.00", None) is None

    def test_ignora_filas_del_catalogo_con_porcentaje_ilegible(self):
        catalogo = [{"id": 1, "type": "IVA", "percentage": "no-es-un-numero"}] + CATALOGO
        assert resolver_impuesto("19.00", catalogo) == 101


class TestIndicePorPorcentaje:
    """El índice es la misma decisión, precalculada para no recorrer el catálogo por línea."""

    def test_el_indice_coincide_con_la_resolucion_directa(self):
        indice = indice_por_porcentaje(CATALOGO)
        for porcentaje in ("19.00", "8.00", "5.00"):
            assert indice.get(round(float(porcentaje), 2)) == resolver_impuesto(
                porcentaje, CATALOGO
            )

    def test_el_indice_no_incluye_el_cero(self):
        indice = indice_por_porcentaje(CATALOGO + [_tax(400, "IVA", 0.0)])
        assert 0.0 not in indice
