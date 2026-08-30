"""Las retenciones que el proveedor declara en el XML, recuperadas y completas.

Qué estaba pasando
------------------
El parser sí extrae `cac:WithholdingTaxTotal`, y en `factura con retenciones.xml` recupera
ReteRenta 3,5 % ($87.113,95) y ReteICA 0,966 % ($24.043,45). Pero al guardar el documento solo
se sumaban los esquemas 06 y 07 en dos columnas —`documents.retefuente` y `documents.reteica`—
que **no se leen en ningún punto del sistema**. Y el esquema 08 (ReteIVA) se descartaba entero.

Para qué sirven
---------------
No son la fuente de verdad: en una factura de compra estas retenciones son las que el
*proveedor* declara, no necesariamente las que la empresa debe practicar. Son la **única señal
independiente** para contrastar lo que Abacus determina — y contrastar es justo lo que hace
falta cuando SIIGO no informa qué retenciones practicó (`PurchasesOut` no trae `retentions`).

Una advertencia sobre las unidades
-----------------------------------
El XML declara la ReteICA como porcentaje verdadero (`0.966`), y el catálogo de SIIGO la
guarda **por mil** (`8.66`). Cualquier comparación entre las dos puntas tiene que atravesar
esa conversión; omitirla retiene diez veces de más.
"""

from app.domain.services.xml_withholdings import (
    ESQUEMAS_DE_RETENCION,
    extraer_retenciones_del_xml,
)


class TestSeRecuperanLosTresEsquemas:
    def test_reconoce_retencion_en_la_fuente(self):
        r = extraer_retenciones_del_xml(
            [{"codigo": "06", "nombre": "ReteRenta", "porcentaje": "3.500",
              "base_imponible": "2488970.00", "valor": "87113.95"}]
        )
        assert len(r) == 1
        assert r[0]["tipo"] == "retefuente"
        assert r[0]["porcentaje"] == 3.5
        assert r[0]["valor"] == 87113.95
        assert r[0]["base"] == 2488970.00

    def test_reconoce_reteica(self):
        r = extraer_retenciones_del_xml(
            [{"codigo": "07", "nombre": "ReteICA", "porcentaje": "0.966",
              "base_imponible": "2488970.00", "valor": "24043.45"}]
        )
        assert r[0]["tipo"] == "reteica"
        assert r[0]["porcentaje"] == 0.966

    def test_reconoce_reteiva_que_antes_se_descartaba(self):
        """El esquema 08 se filtraba fuera al guardar: solo se miraban el 06 y el 07."""
        r = extraer_retenciones_del_xml(
            [{"codigo": "08", "nombre": "ReteIVA", "porcentaje": "15.00",
              "base_imponible": "1000.00", "valor": "150.00"}]
        )
        assert len(r) == 1
        assert r[0]["tipo"] == "reteiva"

    def test_los_tres_esquemas_estan_declarados(self):
        assert set(ESQUEMAS_DE_RETENCION) == {"06", "07", "08"}


class TestVariasRetencionesEnUnDocumento:
    def test_conserva_todas(self):
        """El caso real: ReteRenta y ReteICA en la misma factura."""
        r = extraer_retenciones_del_xml(
            [
                {"codigo": "06", "porcentaje": "3.500", "valor": "87113.95",
                 "base_imponible": "2488970.00"},
                {"codigo": "07", "porcentaje": "0.966", "valor": "24043.45",
                 "base_imponible": "2488970.00"},
            ]
        )
        assert len(r) == 2
        assert {x["tipo"] for x in r} == {"retefuente", "reteica"}

    def test_el_total_retenido_suma_todas(self):
        from app.domain.services.xml_withholdings import total_retenido

        r = extraer_retenciones_del_xml(
            [
                {"codigo": "06", "porcentaje": "3.5", "valor": "87113.95"},
                {"codigo": "07", "porcentaje": "0.966", "valor": "24043.45"},
            ]
        )
        assert total_retenido(r) == 111157.40


class TestLoQueNoEsUnaRetencion:
    def test_ignora_un_esquema_que_no_es_de_retencion(self):
        r = extraer_retenciones_del_xml([{"codigo": "01", "porcentaje": "19.00", "valor": "190"}])
        assert r == []

    def test_una_retencion_con_valor_cero_no_se_practico(self):
        r = extraer_retenciones_del_xml([{"codigo": "06", "porcentaje": "0", "valor": "0"}])
        assert r == []

    def test_sin_retenciones_devuelve_lista_vacia(self):
        assert extraer_retenciones_del_xml([]) == []
        assert extraer_retenciones_del_xml(None) == []


class TestConversionDeUnidadesParaComparar:
    """La ReteICA del XML y la del catálogo de SIIGO están en unidades distintas."""

    def test_la_tarifa_del_xml_se_convierte_a_la_del_catalogo(self):
        from app.domain.services.xml_withholdings import tarifa_en_unidades_de_siigo

        # El XML dice 0.966 %; el catálogo de SIIGO guarda 9.66 por mil.
        assert tarifa_en_unidades_de_siigo(0.966, "reteica") == 9.66

    def test_las_demas_retenciones_no_cambian_de_unidad(self):
        from app.domain.services.xml_withholdings import tarifa_en_unidades_de_siigo

        assert tarifa_en_unidades_de_siigo(3.5, "retefuente") == 3.5
        assert tarifa_en_unidades_de_siigo(15.0, "reteiva") == 15.0
