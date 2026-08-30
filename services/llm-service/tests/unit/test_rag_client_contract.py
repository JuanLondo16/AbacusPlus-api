"""El cliente real del rag-service debe aceptar lo que el recuperador de RF-08 le pide.

Esta prueba existe por un fallo concreto y silencioso: el recuperador de precedentes llamaba
a `search(..., filters=...)` y el cliente real no tenía ese parámetro. La llamada moría en un
`TypeError` que el `except Exception` del recuperador convertía en un warning, así que el
sistema indexaba conocimiento, lo declaraba en la documentación y no recuperaba jamás un
caso: la mitad de RF-08 estaba apagada sin que ningún test lo notara, porque los dobles de
prueba sí aceptaban el parámetro.

De ahí que aquí se use el cliente **real** y se sustituya solo el transporte HTTP. Un doble
que se adelanta a la firma que quisiéramos tener no prueba nada sobre la que tenemos.
"""

import pytest
from app.application.services.retention_evidence import RetentionEvidenceRetriever
from app.infrastructure.clients import rag_client as rag_client_module
from app.infrastructure.clients.rag_client import RagClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    """Transporte falso: registra el cuerpo enviado y devuelve un resultado fijo."""

    def __init__(self):
        self.peticiones: list[dict] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.peticiones.append({"url": url, "json": json})
        return _FakeResponse(
            {
                "results": [
                    {
                        "source_id": 7,
                        "siigo_id": "SIIGO-7",
                        "similarity": 0.9,
                        "content": "CAUSACIÓN CONTABILIZADA",
                        "metadata": {"issuer_nit": "900123456"},
                    }
                ]
            }
        )


@pytest.fixture
def http(monkeypatch):
    fake = _FakeHttpClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(rag_client_module, "get_client", _get_client)
    return fake


class TestBusquedaHibrida:
    @pytest.mark.asyncio
    async def test_el_cliente_real_envia_los_filtros_al_rag_service(self, http):
        client = RagClient(base_url="http://rag-service:8002")

        await client.search(
            "consulta", top_k=3, only_validated=True, filters={"issuer_nit": "900123456"}
        )

        cuerpo = http.peticiones[0]["json"]
        assert cuerpo["filters"] == {"issuer_nit": "900123456"}
        assert cuerpo["only_validated"] is True

    @pytest.mark.asyncio
    async def test_sin_filtros_no_envia_la_clave(self, http):
        """Una búsqueda sin filtros no debe imponer un `filters` vacío al servicio."""
        client = RagClient(base_url="http://rag-service:8002")

        await client.search("consulta")

        assert "filters" not in http.peticiones[0]["json"]

    @pytest.mark.asyncio
    async def test_el_recuperador_de_rf08_obtiene_precedentes_con_el_cliente_real(self, http):
        """La prueba que faltaba: recuperador y cliente reales, uno contra otro."""
        retriever = RetentionEvidenceRetriever(
            rag_client=RagClient(base_url="http://rag-service:8002")
        )

        bundle = await retriever.build(
            document={
                "issuer_nit": "900123456-7",
                "issuer_name": "PROVEEDOR SAS",
                "details": [{"description": "Servicio de transporte"}],
            },
            tipos_candidatos={"retefuente"},
            tarifas_retefuente=[],
            tarifas_reteica=[],
        )

        assert (
            bundle.casos_historicos
        ), "el precedente debe llegar al prompt, no perderse en un warning"
        assert bundle.traza_recuperacion["estrategia"] == "mismo_proveedor"
        # El NIT viaja normalizado: si una parte guarda '900123456' y la otra busca
        # '900123456-7', el historial del proveedor no se encuentra nunca.
        assert http.peticiones[0]["json"]["filters"] == {"issuer_nit": "900123456"}
