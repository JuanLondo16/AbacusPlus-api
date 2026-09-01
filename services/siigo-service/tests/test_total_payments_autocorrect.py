"""Cuando SIIGO dice cuánto esperaba, se le hace caso.

`invalid_total_payments` es el único error que trae la cifra correcta dentro del mensaje:

    "The total payments must be equal to the total purchase.
     The total purchase calculated is 50529.32"

El total depende de cómo esté configurada la empresa —qué retenciones practica el
comprobante, con qué tarifas, sobre qué topes—, y eso cambia sin avisar. Replicar esa
fórmula indefinidamente es frágil; tomar la cifra que SIIGO acaba de publicar, no.

Reenviar es admisible SOLO en este error: es un rechazo de validación, anterior a cualquier
escritura, así que no hay comprobante creado que duplicar. `/v1/purchases` no admite
`Idempotency-Key`, de modo que en cualquier otro caso el reenvío automático está prohibido.
"""

import pytest
from app.application.use_cases.send_purchase_invoice import SendPurchaseInvoiceUseCase
from app.domain.exceptions.base import SiigoApiException

_MENSAJE_REAL = (
    'SIIGO respondió 400: {"status":400,"errors":[{"code":"invalid_total_payments",'
    '"message":"The total payments must be equal to the total purchase. '
    'The total purchase calculated is 50529.32","params":["payments"]}]}'
)


class TestExtraccionDelTotal:
    def test_se_extrae_la_cifra_del_mensaje_real(self):
        exc = SiigoApiException(_MENSAJE_REAL, status_code=400)

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) == 50529.32

    def test_funciona_con_un_total_entero(self):
        exc = SiigoApiException(
            "invalid_total_payments ... The total purchase calculated is 122866",
            status_code=400,
        )

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) == 122866.0

    def test_no_se_reenvia_ante_otro_error_de_siigo(self):
        """Un `invalid_account` no dice nada sobre el pago y pudo tocar otra cosa."""
        exc = SiigoApiException(
            'SIIGO respondió 400: {"code":"invalid_account",'
            '"message":"The account field has an invalid value"}',
            status_code=400,
        )

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) is None

    def test_no_se_reenvia_si_falta_la_cifra(self):
        """Sin el número no hay nada que corregir: el error debe salir tal cual."""
        exc = SiigoApiException(
            "invalid_total_payments: the total payments must be equal", status_code=400
        )

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) is None

    def test_un_timeout_nunca_autoriza_un_reenvio(self):
        """El caso peligroso: la factura pudo crearse y la respuesta perderse."""
        exc = SiigoApiException("SIIGO no respondió dentro del tiempo de espera.", status_code=None)

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) is None

    def test_un_error_de_retenciones_no_autoriza_un_reenvio(self):
        exc = SiigoApiException("invalid_array: The array id has invalid values", status_code=400)

        assert SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc) is None


class TestReenvioUnico:
    """El reenvío ocurre una sola vez y con el valor que SIIGO indicó."""

    class _Cliente:
        def __init__(self, fallos):
            self.fallos = list(fallos)
            self.enviados = []

        def post_document(self, _path, payload):
            import copy

            self.enviados.append(copy.deepcopy(payload))
            if self.fallos:
                raise self.fallos.pop(0)
            return {"id": "05dce9c9", "name": "FC-1-1"}

    def _payload(self):
        return {"payments": [{"id": 4540, "value": 50900.0}], "items": []}

    def test_el_segundo_envio_lleva_el_total_de_siigo(self):
        cliente = self._Cliente([SiigoApiException(_MENSAJE_REAL, status_code=400)])
        payload = self._payload()

        try:
            cliente.post_document("/v1/purchases", payload)
        except SiigoApiException as exc:
            total = SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc)
            payload["payments"][0]["value"] = total
            cliente.post_document("/v1/purchases", payload)

        assert len(cliente.enviados) == 2
        assert cliente.enviados[0]["payments"][0]["value"] == 50900.0
        assert cliente.enviados[1]["payments"][0]["value"] == 50529.32

    def test_si_el_reenvio_tambien_falla_el_error_sale(self):
        """No se insiste: si la cifra de SIIGO tampoco cuadra, el problema es otro."""
        cliente = self._Cliente(
            [
                SiigoApiException(_MENSAJE_REAL, status_code=400),
                SiigoApiException("invalid_account", status_code=400),
            ]
        )
        payload = self._payload()

        with pytest.raises(SiigoApiException):
            try:
                cliente.post_document("/v1/purchases", payload)
            except SiigoApiException as exc:
                payload["payments"][0]["value"] = (
                    SendPurchaseInvoiceUseCase._total_que_espera_siigo(exc)
                )
                cliente.post_document("/v1/purchases", payload)

        assert len(cliente.enviados) == 2
