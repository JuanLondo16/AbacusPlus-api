"""Estructura del cuerpo que se envía a `POST /v1/purchases`.

El campo `retentions` estaba documentado de forma contradictoria por SIIGO: la tabla
descriptiva lo define como «array con los id», pero la estructura formal no lo lista y no hay
ningún ejemplo. Se implementó la lectura literal —enteros sueltos— y el ambiente real la
rechazó con `422 invalid_type: retentions[0]`.

Estas pruebas fijan la forma que SIIGO sí acepta, para que nadie la revierta al leer la tabla
descriptiva sin conocer la respuesta del servidor.
"""

from app.application.dto.purchase_invoice import SendPurchaseInvoiceRequest
from app.application.use_cases.send_purchase_invoice import SendPurchaseInvoiceUseCase


def _peticion(**overrides):
    base = {
        "document_id": 7100,
        "date": "2026-08-22",
        "supplier_identification": "901308499",
        "items": [{"type": "Account", "code": "51951001", "quantity": 1, "price": 556800.0}],
        "payment_id": 5636,
        "payment_value": 556800.0,
    }
    base.update(overrides)
    return SendPurchaseInvoiceRequest(**base)


def _payload(**overrides):
    caso = object.__new__(SendPurchaseInvoiceUseCase)
    return caso._build_payload(_peticion(**overrides))


class TestRetenciones:
    def test_las_retenciones_van_como_objetos_con_id(self):
        """`[{"id": n}]`, no `[n]`. SIIGO rechaza la segunda forma con invalid_type."""
        payload = _payload(retention_ids=[1136, 1137])

        assert payload["retentions"] == [{"id": 1136}, {"id": 1137}]

    def test_sin_retenciones_el_campo_no_se_envia(self):
        """Enviar una lista vacía es distinto de no enviar el campo."""
        assert "retentions" not in _payload(retention_ids=[])

    def test_misma_forma_que_los_impuestos_del_item(self):
        """SIIGO modela ambos igual; divergir fue justamente el origen del rechazo."""
        payload = _payload(
            retention_ids=[1136],
            items=[
                {
                    "type": "Account",
                    "code": "51951001",
                    "quantity": 1,
                    "price": 556800.0,
                    "tax_ids": [13156],
                }
            ],
        )

        assert payload["retentions"][0].keys() == payload["items"][0]["taxes"][0].keys()


class TestNumeroDeFacturaDelProveedor:
    """SIIGO separa el documento del proveedor en `prefix` y `number`.

    `number` solo admite dígitos. Los números de la facturación electrónica colombiana llegan
    de la DIAN como una sola cadena —«FBC98359», «TOFV21215»—, y enviarla entera produce
    `400 invalid_type: number`.
    """

    def test_se_separa_el_prefijo_del_consecutivo(self):
        payload = _payload(provider_invoice_number="FBC98359")

        assert payload["provider_invoice"] == {"prefix": "FBC", "number": "98359"}

    def test_funciona_con_prefijos_de_cualquier_longitud(self):
        payload = _payload(provider_invoice_number="TOFV21215")

        assert payload["provider_invoice"] == {"prefix": "TOFV", "number": "21215"}

    def test_un_numero_sin_prefijo_usa_el_prefijo_por_defecto(self):
        """`provider_invoice` es obligatorio, y con sus dos campos.

        El esquema del blueprint no lo lista entre los `required` del documento, pero la API
        real discrepa y manda ella. Se comprobaron los dos caminos contra el ambiente real:

        - bloque sin `prefix`  → `The field provider_invoice.prefix is required`
        - sin el bloque entero → `The field provider_invoice is required`

        Luego un número sin prefijo necesita uno de todos modos.
        """
        payload = _payload(provider_invoice_number="98359")

        assert payload["provider_invoice"] == {"prefix": "FV", "number": "98359"}

    def test_el_prefijo_explicito_manda_sobre_el_deducido(self):
        """Quien lo configuró conoce la nomenclatura de ese proveedor."""
        payload = _payload(
            provider_invoice_prefix="FE", provider_invoice_number="98359"
        )

        assert payload["provider_invoice"] == {"prefix": "FE", "number": "98359"}

    def test_el_prefijo_explicito_no_se_duplica_en_el_numero(self):
        payload = _payload(
            provider_invoice_prefix="FBC", provider_invoice_number="FBC98359"
        )

        assert payload["provider_invoice"] == {"prefix": "FBC", "number": "98359"}

    def test_un_valor_sin_digitos_no_envia_el_bloque(self):
        """`number` «solo admite números»: sin consecutivo no hay bloque que construir.

        Es el único caso en que se omite: el prefijo tiene sustituto por defecto, el
        consecutivo no —inventarlo sería inventar el número de la factura del proveedor—.
        """
        payload = _payload(provider_invoice_number="SINDIGITOS")

        assert "provider_invoice" not in payload

    def test_sin_numero_ni_prefijo_no_se_envia_el_bloque(self):
        assert "provider_invoice" not in _payload()

    def test_el_prefijo_configurado_no_deja_letras_en_el_consecutivo(self):
        """El caso real del documento 30: prefijo de empresa, número de otro proveedor.

        El prefijo que se configura en la plantilla es el de la empresa; el número llega del
        proveedor. Cuando no coinciden —«G3Z9338669» con prefijo «FE»— retirar el prefijo no
        quita nada, y antes el resto viajaba con letras dentro de `number`. SIIGO respondía
        `invalid_type: number`, que es como fallaron los documentos 26 y 30.
        """
        payload = _payload(
            provider_invoice_prefix="FE", provider_invoice_number="G3Z9338669"
        )

        assert payload["provider_invoice"] == {"prefix": "FE", "number": "9338669"}
        assert payload["provider_invoice"]["number"].isdigit()

    def test_los_numeros_reales_que_fallaron_quedan_solo_en_digitos(self):
        for numero in ("G3Z9338669", "F78P21635", "003B54597", "B9051102032"):
            payload = _payload(
                provider_invoice_prefix="FE", provider_invoice_number=numero
            )

            assert payload["provider_invoice"]["number"].isdigit(), numero

    def test_con_prefijo_explicito_un_valor_sin_digitos_tampoco_se_envia(self):
        """Hay prefijo, pero sigue sin haber consecutivo: el bloque quedaría incompleto."""
        payload = _payload(
            provider_invoice_prefix="FE", provider_invoice_number="SINDIGITOS"
        )

        assert "provider_invoice" not in payload


class TestConsecutivoDelComprobante:
    """Numeración manual: el consecutivo lo pone quien envía, no SIIGO.

    El tipo de comprobante de compra puede estar configurado con `automatic_number: false`.
    En ese modo SIIGO no asigna el número y lo exige en el cuerpo; sin él responde
    `parameter_required` sobre el campo `number`, que es exactamente lo que rechazó al
    primer documento enviado a producción.
    """

    _MANUAL = {"id": 19693, "automatic_number": False, "consecutive": 202608018}
    _AUTOMATICO = {"id": 19693, "automatic_number": True, "consecutive": 202608018}

    def _payload_con_tipo(self, tipo):
        caso = object.__new__(SendPurchaseInvoiceUseCase)
        return caso._build_payload(_peticion(), tipo)

    def test_con_numeracion_manual_se_envia_el_consecutivo(self):
        assert self._payload_con_tipo(self._MANUAL)["number"] == 202608018

    def test_con_numeracion_automatica_no_se_envia(self):
        """Enviarlo sería pisar el consecutivo que SIIGO administra."""
        assert "number" not in self._payload_con_tipo(self._AUTOMATICO)

    def test_sin_configuracion_conocida_no_se_inventa(self):
        assert "number" not in self._payload_con_tipo(None)

    def test_numeracion_manual_sin_consecutivo_se_detiene_antes_de_enviar(self):
        """Sin número no hay envío posible: mejor un mensaje que un 400 de SIIGO."""
        import pytest
        from app.domain.exceptions.base import ValidationException

        with pytest.raises(ValidationException, match="numeración manual"):
            self._payload_con_tipo({"id": 19693, "automatic_number": False})

    def test_el_prefijo_se_recorta_a_seis_caracteres(self):
        """«alfanumérico de máximo 6 caracteres»."""
        payload = _payload(
            provider_invoice_prefix="PREFIJOLARGO", provider_invoice_number="123"
        )

        assert payload["provider_invoice"]["prefix"] == "PREFIJ"

    def test_un_consecutivo_de_mas_de_once_digitos_no_se_recorta(self):
        """«debe ser de 11 enteros».

        Recortarlo lo convertiría en un número distinto del que aparece en la factura del
        proveedor, que es justo lo que este campo sirve para cruzar. Se omite el bloque.
        """
        payload = _payload(provider_invoice_number="FE123456789012345")

        assert "provider_invoice" not in payload

    def test_un_consecutivo_de_once_digitos_si_se_envia(self):
        payload = _payload(provider_invoice_number="FE12345678901")

        assert payload["provider_invoice"] == {"prefix": "FE", "number": "12345678901"}

    def test_el_documento_de_la_prueba_real_viaja_completo(self):
        """«941457814» es solo dígitos: toma el prefijo por defecto y el bloque va entero."""
        payload = _payload(provider_invoice_number="941457814")

        assert payload["provider_invoice"] == {"prefix": "FV", "number": "941457814"}

    def test_el_prefijo_deducido_manda_sobre_el_por_defecto(self):
        """Si el proveedor sí usa prefijo, se respeta el suyo."""
        payload = _payload(provider_invoice_number="FBC98359")

        assert payload["provider_invoice"]["prefix"] == "FBC"

    def test_el_prefijo_configurado_manda_sobre_el_por_defecto(self):
        payload = _payload(
            provider_invoice_prefix="SP", provider_invoice_number="941457814"
        )

        assert payload["provider_invoice"]["prefix"] == "SP"
