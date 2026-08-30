"""La interfaz y el envío deciden sobre lo mismo.

Estaban decidiendo distinto: el selector ofrecía todo el catálogo sincronizado y el envío
descartaba lo que la API rechaza. El contador registraba una Retefuente, Abacus la descontaba
del total a pagar y SIIGO contabilizaba el importe íntegro. Dos pantallas, dos verdades y una
diferencia silenciosa sobre dinero de un tercero: en el documento 941457814 fueron 199.553,84.

La única forma de que no diverjan es que lean la misma lista, y por eso vive sola en el
dominio en vez de estar copiada en cada capa.
"""

from app.application.use_cases.account_document import AccountDocumentUseCase
from app.domain.value_objects.retention_scope import (
    TIPOS_DE_RETENCION_EN_COMPRAS,
    es_impuesto_de_linea,
    es_retencion_practicable,
)


class TestLoPracticable:
    def test_reteica_y_reteiva_son_las_admitidas(self):
        """«Array con los id de los impuestos tipo ReteICA, ReteIVA» (POST /v1/purchases)."""
        assert es_retencion_practicable("ReteICA")
        assert es_retencion_practicable("ReteIVA")

    def test_los_tipos_rechazados_no_lo_son(self):
        """Comprobado contra el ambiente real: rechazados en `retentions` y en los ítems."""
        for tipo in ("Retefuente", "Autorretencion", "Impoconsumo", "IVA", "AdValorem"):
            assert not es_retencion_practicable(tipo), tipo

    def test_el_tipo_se_compara_sin_distinguir_mayusculas(self):
        for tipo in ("reteica", "RETEICA", " ReteICA "):
            assert es_retencion_practicable(tipo)

    def test_un_tipo_vacio_no_es_practicable(self):
        assert not es_retencion_practicable(None)
        assert not es_retencion_practicable("")


class TestUnaSolaFuenteDeVerdad:
    def test_el_envio_usa_la_lista_del_dominio(self):
        """Si divergen, vuelve la diferencia entre lo que se ve y lo que se contabiliza."""
        assert (
            AccountDocumentUseCase.TIPOS_DE_RETENCION_ACEPTADOS
            is TIPOS_DE_RETENCION_EN_COMPRAS
        )

    def test_lo_que_el_selector_ofrece_es_lo_que_el_envio_manda(self):
        """El invariante que cierra el descuadre, comprobado tipo por tipo."""
        for tipo in ("ReteICA", "ReteIVA", "Retefuente", "Autorretencion", "Impoconsumo"):
            ofrecido = es_retencion_practicable(tipo)
            enviado = (
                tipo.strip().lower()
                in AccountDocumentUseCase.TIPOS_DE_RETENCION_ACEPTADOS
            )
            assert ofrecido == enviado, tipo


class TestImpuestosDeLinea:
    """La contraparte: lo que se asigna a un ítem y SUMA al valor de la operación.

    SIIGO reparte el catálogo en dos sitios del comprobante, y un tipo en el sitio equivocado
    no falla: se comporta al revés. Un impuesto puesto donde va una retención se resta en
    lugar de sumarse, y eso descuadró cuatro documentos con el impuesto al consumo.
    """

    def test_los_impuestos_de_linea_son_los_que_suman(self):
        for tipo in ("IVA", "Impoconsumo", "AdValorem"):
            assert es_impuesto_de_linea(tipo), tipo

    def test_las_retenciones_no_son_impuestos_de_linea(self):
        """«Si envías un reteIVA o reteICA en los items de factura» → error."""
        for tipo in ("ReteIVA", "ReteICA", "Retefuente", "Autorretencion"):
            assert not es_impuesto_de_linea(tipo), tipo

    def test_ningun_tipo_cae_en_los_dos_ambitos(self):
        """El invariante que impide que un tipo se ofrezca en el selector equivocado."""
        for tipo in (
            "IVA", "Impoconsumo", "AdValorem",
            "ReteIVA", "ReteICA", "Retefuente", "Autorretencion",
        ):
            assert not (es_impuesto_de_linea(tipo) and es_retencion_practicable(tipo)), tipo

    def test_el_impoconsumo_es_de_linea_y_no_retencion(self):
        """Confirmado contra el ambiente real con la factura F78P21635.

        SIIGO devolvió `Impoconsumo 8%` aplicado en sus dos líneas (5.844,44 y 362,96) y el
        total intacto en 83.800. Estaba registrado como retención, donde restaba y además no
        se enviaba.
        """
        assert es_impuesto_de_linea("Impoconsumo")
        assert not es_retencion_practicable("Impoconsumo")

    def test_se_compara_sin_distinguir_mayusculas(self):
        for tipo in ("impoconsumo", "IMPOCONSUMO", " Impoconsumo "):
            assert es_impuesto_de_linea(tipo)

    def test_un_tipo_vacio_no_es_de_linea(self):
        assert not es_impuesto_de_linea(None)
        assert not es_impuesto_de_linea("")
