"""
RF-08 — Disparo automático de la determinación de retenciones.

El alcance pide que la IA determine las retenciones «durante el procesamiento de cada
documento», no solo cuando el contador pulsa el botón. Este cliente es ese disparo.

Dos garantías se prueban aquí. La primera es que se pide `persist=true`: en el
procesamiento automático nadie recibe la respuesta, así que si no se guardara, la
determinación no serviría de nada. La segunda es que nada de esto puede tumbar el
procesamiento del XML —el documento ya está guardado cuando se llega a este punto—, de
modo que cualquier fallo del llm-service se registra y se sigue adelante.
"""

import httpx
import pytest
from app.infrastructure.clients.llm_client import LlmClient


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Sustituto de httpx.AsyncClient que registra la llamada en vez de emitirla."""

    calls: list[dict] = []
    response = _FakeResponse(200, {"persisted": {"created": 2, "skipped": 0}})
    raises: Exception = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, params=None):
        type(self).calls.append({"url": url, "headers": headers, "params": params})
        if type(self).raises is not None:
            raise type(self).raises
        return type(self).response


@pytest.fixture
def fake_http(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = _FakeResponse(200, {"persisted": {"created": 2, "skipped": 0}})
    _FakeAsyncClient.raises = None
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def client():
    return LlmClient(base_url="http://llm-service:8003", bearer_token="tok")


class TestTheAutomaticTrigger:
    @pytest.mark.asyncio
    async def test_it_calls_the_retention_suggestion_endpoint(self, client, fake_http):
        await client.trigger_retention_suggestion(42)

        assert fake_http.calls[0]["url"] == (
            "http://llm-service:8003/api/v1/accounting/retention-suggestions/42"
        )

    @pytest.mark.asyncio
    async def test_it_asks_for_the_proposal_to_be_persisted(self, client, fake_http):
        """Sin persistir, la determinación automática se perdería: nadie la escucha."""
        await client.trigger_retention_suggestion(42)

        assert fake_http.calls[0]["params"] == {"persist": "true"}

    @pytest.mark.asyncio
    async def test_it_forwards_the_caller_credentials(self, client, fake_http):
        await client.trigger_retention_suggestion(42)

        assert fake_http.calls[0]["headers"] == {"Authorization": "Bearer tok"}


class TestItNeverBreaksTheDocumentProcessing:
    """El documento ya está guardado; un fallo aquí no puede propagarse."""

    @pytest.mark.asyncio
    async def test_a_transport_error_is_swallowed(self, client, fake_http):
        fake_http.raises = httpx.ConnectError("sin ruta al host")

        await client.trigger_retention_suggestion(42)  # no debe elevar

    @pytest.mark.asyncio
    async def test_a_missing_chart_of_accounts_is_an_expected_outcome(self, client, fake_http):
        """El 409 del RF-08 es una condición de negocio, no una falla del sistema."""
        fake_http.response = _FakeResponse(409, {"detail": "No tienes un plan único de cuenta"})

        await client.trigger_retention_suggestion(42)

    @pytest.mark.asyncio
    async def test_an_unexpected_status_is_swallowed(self, client, fake_http):
        fake_http.response = _FakeResponse(500, {})

        await client.trigger_retention_suggestion(42)

    @pytest.mark.asyncio
    async def test_a_malformed_body_is_swallowed(self, client, fake_http):
        class _Broken(_FakeResponse):
            def json(self):
                raise ValueError("no es json")

        fake_http.response = _Broken(200)

        await client.trigger_retention_suggestion(42)
