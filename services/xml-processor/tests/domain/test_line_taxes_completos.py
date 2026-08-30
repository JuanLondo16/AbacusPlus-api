"""Una línea puede llevar más de un impuesto, y hay que conservarlos todos.

El defecto, medido
------------------
Al construir las líneas se tomaba `(item["impuestos"] or [{}])[0]`: el primer subtotal de
impuesto y nada más. Todo lo demás se descartaba sin dejar rastro.

Contrastando `documents.total_taxes` contra la suma de `document_details.tax_value` sobre los
45 XML reales del cliente: **19 documentos pierden impuesto, por un total de $7.363,44**.

La causa concreta son ocho facturas de telecomunicaciones que declaran, en la MISMA línea:

    <cac:TaxSubtotal> IVA 19 % </cac:TaxSubtotal>
    <cac:TaxSubtotal> INC  4 % </cac:TaxSubtotal>

Se conservaba el IVA y se perdía el impuesto al consumo. Después, la línea de ajuste que el
sistema añade para cuadrar el total tapaba el hueco — y por eso el defecto nunca tuvo síntoma:
el documento se contabilizaba en verde, por el importe correcto, con la naturaleza contable
equivocada.

Estas pruebas fijan que la extracción conserve la lista completa.
"""

from app.domain.services.line_taxes import extraer_impuestos_de_linea


class TestSeConservanTodosLosImpuestos:
    def test_una_linea_con_iva_e_impuesto_al_consumo_conserva_los_dos(self):
        """El caso real de las ocho facturas de telecomunicaciones."""
        impuestos = extraer_impuestos_de_linea(
            [
                {"codigo": "01", "nombre": "IVA", "porcentaje": "19.00",
                 "base_imponible": "99577.63", "valor": "18919.75"},
                {"codigo": "04", "nombre": "INC", "porcentaje": "4.00",
                 "base_imponible": "99577.63", "valor": "3983.11"},
            ]
        )
        assert len(impuestos) == 2
        assert [i["porcentaje"] for i in impuestos] == [19.0, 4.0]
        assert [i["esquema"] for i in impuestos] == ["01", "04"]

    def test_el_valor_total_de_la_linea_suma_todos_sus_impuestos(self):
        """Es la cifra que se compara contra `documents.total_taxes`.

        Con solo el primero, esta suma se quedaba corta y la diferencia acababa en una línea
        de ajuste que la hacía invisible.
        """
        impuestos = extraer_impuestos_de_linea(
            [
                {"codigo": "01", "porcentaje": "19.00", "valor": "18919.75"},
                {"codigo": "04", "porcentaje": "4.00", "valor": "3983.11"},
            ]
        )
        assert round(sum(i["valor"] for i in impuestos), 2) == 22902.86

    def test_una_linea_con_un_solo_impuesto_sigue_funcionando_igual(self):
        impuestos = extraer_impuestos_de_linea(
            [{"codigo": "04", "porcentaje": "8.00", "base_imponible": "73055.56",
              "valor": "5844.44"}]
        )
        assert len(impuestos) == 1
        assert impuestos[0]["porcentaje"] == 8.0
        assert impuestos[0]["valor"] == 5844.44


class TestImpuestosSinPorcentaje:
    def test_conserva_el_impuesto_por_unidad(self):
        """INC Bolsas es un monto fijo por bolsa: llega sin `cbc:Percent`.

        No se descarta por no tener porcentaje — su valor es dinero real que forma parte del
        total de la factura.
        """
        impuestos = extraer_impuestos_de_linea(
            [{"codigo": "22", "nombre": "INC Bolsas", "porcentaje": None,
              "valor_por_unidad": "73.00", "valor": "73.00"}]
        )
        assert len(impuestos) == 1
        assert impuestos[0]["porcentaje"] == 0.0
        assert impuestos[0]["valor"] == 73.0
        assert impuestos[0]["por_unidad"] == 73.0

    def test_conserva_el_impuesto_al_consumo_de_voz(self):
        """Esquema 02, presente en un documento real, sin porcentaje declarado."""
        impuestos = extraer_impuestos_de_linea(
            [{"codigo": "02", "nombre": "IC", "porcentaje": None, "valor": "192.00"}]
        )
        assert impuestos[0]["esquema"] == "02"
        assert impuestos[0]["valor"] == 192.0


class TestLineasSinImpuesto:
    def test_una_linea_exenta_no_produce_impuestos(self):
        assert extraer_impuestos_de_linea([]) == []
        assert extraer_impuestos_de_linea(None) == []

    def test_descarta_el_esquema_zz_de_no_aplica(self):
        """«ZZ» es literalmente «No aplica»: no es un impuesto que enlazar ni que sumar."""
        impuestos = extraer_impuestos_de_linea(
            [{"codigo": "ZZ", "nombre": "No aplica", "porcentaje": "0.00", "valor": "0.00"}]
        )
        assert impuestos == []

    def test_descarta_un_impuesto_de_cero_sin_valor(self):
        """Un IVA al 0 % sin importe no cambia el total y añade una referencia que puede
        fallar en SIIGO."""
        impuestos = extraer_impuestos_de_linea(
            [{"codigo": "01", "porcentaje": "0.00", "valor": "0.00"}]
        )
        assert impuestos == []


class TestElImpuestoPrincipal:
    """`tax_type` y `tax_value` siguen existiendo: son el impuesto principal de la línea."""

    def test_el_principal_es_el_de_mayor_valor(self):
        """Con IVA 19 % e INC 4 %, el principal es el IVA.

        No se toma «el primero que venga» sino el de mayor importe, que es el que describe la
        naturaleza de la línea. Así la interfaz y el RAG, que leen estos dos campos, siguen
        mostrando lo relevante mientras la lista completa alimenta el envío.
        """
        from app.domain.services.line_taxes import impuesto_principal

        impuestos = extraer_impuestos_de_linea(
            [
                {"codigo": "04", "porcentaje": "4.00", "valor": "3983.11"},
                {"codigo": "01", "porcentaje": "19.00", "valor": "18919.75"},
            ]
        )
        principal = impuesto_principal(impuestos)
        assert principal["porcentaje"] == 19.0

    def test_sin_impuestos_el_principal_es_nulo(self):
        from app.domain.services.line_taxes import impuesto_principal

        assert impuesto_principal([]) is None
