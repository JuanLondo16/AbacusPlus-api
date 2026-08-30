"""La configuración del comprobante decide, no una suposición nuestra.

`GET /v1/document-types?type=FC` devuelve, entre otras banderas, `consumption_tax`: «Indica
si el documento maneja impuesto al consumo». El código ya lee de ese mismo objeto
`cost_center_mandatory` y `automatic_number`, pero ignoraba ésta.

Mientras tanto añadía una línea de ajuste contra una cuenta de impuesto al consumo cada vez
que el total no cuadraba, sin preguntar si el comprobante admite ese impuesto por la vía
nativa —`items[].taxes`, comprobada en la factura F78P21635—.

Se expone la bandera para que la decisión la tome la configuración de la empresa, que es quien
la conoce, y no una regla escrita aquí.
"""

from app.application.use_cases.send_purchase_invoice import SendPurchaseInvoiceUseCase


class TestLecturaDeLaBandera:
    def test_un_comprobante_que_admite_impuesto_al_consumo(self):
        assert (
            SendPurchaseInvoiceUseCase.admite_impuesto_al_consumo(
                {"id": 1, "consumption_tax": True}
            )
            is True
        )

    def test_un_comprobante_que_no_lo_admite(self):
        assert (
            SendPurchaseInvoiceUseCase.admite_impuesto_al_consumo(
                {"id": 1, "consumption_tax": False}
            )
            is False
        )

    def test_sin_catalogo_no_se_afirma_nada(self):
        """None significa «no se pudo consultar», no «no lo admite».

        Es la misma postura que ya se aplica al centro de costo: sin catálogo disponible no se
        bloquea ni se inventa una regla, se envía y decide SIIGO. Devolver False aquí haría
        que un fallo de red cambiara la forma de contabilizar.
        """
        assert SendPurchaseInvoiceUseCase.admite_impuesto_al_consumo(None) is None
        assert SendPurchaseInvoiceUseCase.admite_impuesto_al_consumo({}) is None

    def test_una_bandera_ilegible_se_trata_como_desconocida(self):
        assert (
            SendPurchaseInvoiceUseCase.admite_impuesto_al_consumo(
                {"consumption_tax": "quizá"}
            )
            is None
        )


class TestLaBanderaViajaEnLaRespuesta:
    """El xml-processor necesita saberlo para elegir entre la vía nativa y la de ajuste."""

    def test_la_respuesta_declara_el_campo(self):
        from app.application.dto.purchase_invoice import SendPurchaseInvoiceResponse

        assert "supports_consumption_tax" in SendPurchaseInvoiceResponse.model_fields
