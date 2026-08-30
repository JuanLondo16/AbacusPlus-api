"""El catálogo de impuestos debe llegar también cuando no hay usuario detrás.

El problema que fija esta prueba
--------------------------------
`document_details.tax_id` es el enlace entre una línea de la factura y el impuesto del
catálogo. Sirve para dos cosas: que la interfaz muestre qué impuesto lleva la línea, y que el
envío a SIIGO respete lo que el contador eligió (`if detail.tax_id: return detail.tax_id`).

En la base del cliente, de 152 líneas al 19 % solo **una** tenía `tax_id`. La causa no era el
emparejamiento sino el origen: la descarga masiva desde la DIAN construye el caso de uso sin
cliente de catálogo, y cuando lo había, la ruta con JWT respondía 403 y el `except` del
cliente devolvía lista vacía. Un fallo total, silencioso y sin ningún síntoma visible.

La corrección es la misma que ya usan el siigo-service y el rag-service: cuando hay
`tenant_slug` se habla por la ruta interna, con `X-Internal-Secret`.
"""


import pytest
from app.infrastructure.clients.integration_config_client import IntegrationConfigClient


class TestRutaSegunElOrigenDeLaLlamada:
    """Qué ruta y qué credencial usa el cliente según quién lo construyó."""

    def test_con_tenant_slug_usa_la_ruta_interna(self):
        """Un worker sin usuario habla por `/internal/taxes`.

        Es la diferencia que hacía que el catálogo no llegara nunca en la descarga masiva.
        """
        cliente = IntegrationConfigClient(
            base_url="http://integration-config-service:8007", tenant_slug="ikbo"
        )
        assert cliente.taxes_path == "/internal/taxes"

    def test_sin_tenant_slug_conserva_la_ruta_con_token(self):
        """La vía del usuario no cambia: sigue por `/api/v1/integrations/taxes`."""
        cliente = IntegrationConfigClient(
            base_url="http://integration-config-service:8007", bearer_token="jwt-de-usuario"
        )
        assert cliente.taxes_path == "/api/v1/integrations/taxes"

    def test_la_ruta_interna_viaja_con_el_secreto_y_el_tenant(self, monkeypatch):
        """Autentica con `X-Internal-Secret` y elige base con `X-Tenant-Slug`.

        Sin el secreto la llamada sería anónima contra un servicio alcanzable desde la red del
        clúster; sin el tenant, el servicio no sabría sobre qué base responder.
        """
        monkeypatch.setenv("INTERNAL_SECRET", "secreto-de-prueba")
        cliente = IntegrationConfigClient(
            base_url="http://integration-config-service:8007", tenant_slug="ikbo"
        )
        assert cliente.headers["X-Internal-Secret"] == "secreto-de-prueba"
        assert cliente.headers["X-Tenant-Slug"] == "ikbo"
        assert "Authorization" not in cliente.headers

    def test_la_ruta_con_token_no_manda_cabeceras_internas(self):
        """El secreto interno no se filtra a una llamada que ya tiene JWT."""
        cliente = IntegrationConfigClient(
            base_url="http://integration-config-service:8007", bearer_token="jwt-de-usuario"
        )
        assert "X-Internal-Secret" not in cliente.headers
        assert cliente.headers["Authorization"] == "Bearer jwt-de-usuario"


class TestElFalloDejaDeSerSilencioso:
    """Que el catálogo no llegue debe constar, no desaparecer."""

    @pytest.mark.asyncio
    async def test_un_catalogo_vacio_queda_registrado(self, caplog):
        """Si la consulta falla, se registra con nivel de aviso y con la URL.

        El `except` que devolvía `[]` sin más es lo que permitió que el defecto viviera
        meses: el documento se guardaba, nadie veía un error, y todas las líneas quedaban
        sin impuesto.
        """
        cliente = IntegrationConfigClient(
            base_url="http://destino-que-no-existe:9", tenant_slug="ikbo"
        )
        with caplog.at_level("WARNING"):
            resultado = await cliente.get_taxes()
        assert resultado == []
        assert any("impuesto" in r.message.lower() for r in caplog.records)
