import pytest
from datetime import datetime, timedelta

from app.application.use_cases.proxy_request import ProxyRequestUseCase
from app.application.dto.proxy import ProxyRequest
from app.domain.entities.session import SessionEntity
from app.domain.ports.services import ExternalClientPort
from app.domain.exceptions.base import SessionNotFoundException
from app.infrastructure.session.in_memory_store import InMemorySessionStore

_FAKE_COOKIES = {"session": "abc123"}
_FAKE_RESPONSE = {"status_code": 200, "body": {"result": "ok"}, "headers": {}}


class FakeExternalClient(ExternalClientPort):
    def __init__(self, response: dict = None):
        self._response = response or _FAKE_RESPONSE
        self.last_call: dict = {}

    async def login(self, login_url, credentials):
        return {}

    async def request(self, method, url, cookies, body=None, params=None):
        self.last_call = {"method": method, "url": url, "cookies": cookies}
        return self._response


def _make_use_case(client=None, base_url="https://portal.example.com"):
    store = InMemorySessionStore(ttl_seconds=3600)
    session = SessionEntity(session_id="test-session-id", cookies=_FAKE_COOKIES)
    store.save(session)
    use_case = ProxyRequestUseCase(
        session_store=store,
        external_client=client or FakeExternalClient(),
        base_url=base_url,
    )
    return use_case, store


@pytest.mark.asyncio
async def test_returns_proxy_response():
    use_case, _ = _make_use_case()
    result = await use_case.execute(
        ProxyRequest(session_id="test-session-id", method="GET", path="/api/data")
    )
    assert result.status_code == 200
    assert result.body == {"result": "ok"}


@pytest.mark.asyncio
async def test_raises_when_session_not_found():
    use_case, _ = _make_use_case()
    with pytest.raises(SessionNotFoundException):
        await use_case.execute(
            ProxyRequest(session_id="nonexistent", method="GET", path="/api/data")
        )


@pytest.mark.asyncio
async def test_cookies_are_passed_to_client():
    client = FakeExternalClient()
    use_case, _ = _make_use_case(client=client)
    await use_case.execute(
        ProxyRequest(session_id="test-session-id", method="POST", path="/api/submit", body={"x": 1})
    )
    assert client.last_call["cookies"] == _FAKE_COOKIES


@pytest.mark.asyncio
async def test_full_url_is_constructed_correctly():
    client = FakeExternalClient()
    use_case, _ = _make_use_case(client=client, base_url="https://portal.example.com")
    await use_case.execute(
        ProxyRequest(session_id="test-session-id", method="GET", path="/api/invoices")
    )
    assert client.last_call["url"] == "https://portal.example.com/api/invoices"


@pytest.mark.asyncio
async def test_expired_session_raises_not_found():
    store = InMemorySessionStore(ttl_seconds=1)
    session = SessionEntity(
        session_id="expired-session",
        cookies=_FAKE_COOKIES,
        last_accessed_at=datetime.utcnow() - timedelta(seconds=10),
    )
    # Inyectamos directamente la sesión expirada
    store._store["expired-session"] = session
    use_case = ProxyRequestUseCase(
        session_store=store,
        external_client=FakeExternalClient(),
        base_url="https://portal.example.com",
    )
    with pytest.raises(SessionNotFoundException):
        await use_case.execute(
            ProxyRequest(session_id="expired-session", method="GET", path="/api/data")
        )
