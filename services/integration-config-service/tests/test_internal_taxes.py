"""El catálogo de impuestos, accesible servicio-a-servicio.

Por qué existe este endpoint
----------------------------
El xml-processor necesita el catálogo de impuestos al PROCESAR un XML, para enlazar cada
línea con el impuesto que le corresponde (`document_details.tax_id`). Pero la vía por la que
llega la mayoría de los documentos —la descarga masiva desde la DIAN— corre en segundo plano,
sin ningún JWT de usuario: allí el `ProcessXmlUseCase` se construía directamente y la llamada
al catálogo, cuando existía, respondía 403 y el `except` la dejaba en lista vacía.

El efecto era silencioso y total: de 152 líneas al 19 % en la base del cliente, **una sola**
quedó con `tax_id`. La interfaz mostraba las líneas sin impuesto y la rama «el contador ya
eligió el impuesto» del envío no se ejecutaba nunca.

Se sigue el mismo patrón que ya usan `/internal/retention-criteria` y `/internal/fiscal-profile`
para el llm-service: `X-Internal-Secret` para autenticar y `X-Tenant-Slug` para elegir la base.
"""


import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "secreto-de-prueba")
    from app.main import app

    return TestClient(app)


class TestInternalTaxesEndpoint:
    """Contrato del endpoint interno del catálogo de impuestos."""

    def test_rechaza_peticion_sin_secreto_interno(self, client):
        """Sin `X-Internal-Secret` no se entrega el catálogo.

        El catálogo describe la configuración tributaria de una empresa: no puede quedar
        abierto por ser «interno», porque el servicio es alcanzable desde la red del clúster.
        """
        respuesta = client.get(
            "/internal/taxes", headers={"X-Tenant-Slug": "ikbo"}
        )
        assert respuesta.status_code in (401, 403, 422)

    def test_rechaza_secreto_interno_incorrecto(self, client):
        """Un secreto que no coincide se rechaza, no se ignora."""
        respuesta = client.get(
            "/internal/taxes",
            headers={"X-Internal-Secret": "otro", "X-Tenant-Slug": "ikbo"},
        )
        assert respuesta.status_code in (401, 403)

    def test_exige_el_tenant(self, client):
        """Sin `X-Tenant-Slug` no hay base sobre la que responder."""
        respuesta = client.get(
            "/internal/taxes", headers={"X-Internal-Secret": "secreto-de-prueba"}
        )
        assert respuesta.status_code == 422

    def test_el_endpoint_existe(self, client):
        """Con secreto y tenant, la ruta resuelve.

        No se comprueba el contenido —depende de la base del cliente— sino que la ruta exista
        y no responda 404. Es la comprobación que faltaba: hasta ahora el xml-processor pedía
        un catálogo por una puerta que solo aceptaba JWT de usuario.
        """
        respuesta = client.get(
            "/internal/taxes",
            headers={"X-Internal-Secret": "secreto-de-prueba", "X-Tenant-Slug": "ikbo"},
        )
        assert respuesta.status_code != 404
