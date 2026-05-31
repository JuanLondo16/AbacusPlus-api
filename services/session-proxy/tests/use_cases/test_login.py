import pytest
from app.application.dto.auth import LoginRequest
from app.application.use_cases.login import LoginUseCase
from app.domain.exceptions.base import ExternalAuthException
from app.domain.ports.services import ExternalClientPort
from app.infrastructure.session.in_memory_store import InMemorySessionStore


class FakeExternalClient(ExternalClientPort):
    async def login(self, login_url: str, credentials: dict) -> dict:
        return {"session": "abc123", "csrftoken": "xyz"}

    async def request(self, method, url, cookies, body=None, params=None):
        return {"status_code": 200, "body": {}, "headers": {}}

    async def login_and_request(
        self,
        login_url: str,
        credentials: dict,
        method: str,
        url: str,
        body=None,
        params=None,
    ) -> dict:
        cookies = await self.login(login_url=login_url, credentials=credentials)
        return await self.request(method=method, url=url, cookies=cookies, body=body, params=params)

    async def login_and_download(
        self, login_url: str, credentials: dict, download_url: str
    ) -> bytes:
        return b""


class EmptyCookieClient(ExternalClientPort):
    async def login(self, login_url: str, credentials: dict) -> dict:
        return {}

    async def request(self, method, url, cookies, body=None, params=None):
        return {}

    async def login_and_request(
        self,
        login_url: str,
        credentials: dict,
        method: str,
        url: str,
        body=None,
        params=None,
    ) -> dict:
        cookies = await self.login(login_url=login_url, credentials=credentials)
        return await self.request(method=method, url=url, cookies=cookies, body=body, params=params)

    async def login_and_download(
        self, login_url: str, credentials: dict, download_url: str
    ) -> bytes:
        return b""


@pytest.mark.asyncio
async def test_creates_session_and_returns_session_id():
    store = InMemorySessionStore(ttl_seconds=3600)
    use_case = LoginUseCase(
        session_store=store,
        external_client=FakeExternalClient(),
        login_url="https://portal.example.com/api/login",
    )
    result = await use_case.execute(LoginRequest(token="mi-token"))

    assert result.session_id
    assert len(result.session_id) == 36  # UUID4


@pytest.mark.asyncio
async def test_session_stored_with_cookies():
    store = InMemorySessionStore(ttl_seconds=3600)
    use_case = LoginUseCase(
        session_store=store,
        external_client=FakeExternalClient(),
        login_url="https://portal.example.com/api/login",
    )
    result = await use_case.execute(LoginRequest(token="mi-token"))

    session = store.get(result.session_id)
    assert session is not None
    assert session.cookies == {"session": "abc123", "csrftoken": "xyz"}


@pytest.mark.asyncio
async def test_raises_when_no_cookies_returned():
    store = InMemorySessionStore(ttl_seconds=3600)
    use_case = LoginUseCase(
        session_store=store,
        external_client=EmptyCookieClient(),
        login_url="https://portal.example.com/api/login",
    )
    with pytest.raises(ExternalAuthException):
        await use_case.execute(LoginRequest(token="bad-token"))


@pytest.mark.asyncio
async def test_each_login_produces_unique_session_id():
    store = InMemorySessionStore(ttl_seconds=3600)
    use_case = LoginUseCase(
        session_store=store,
        external_client=FakeExternalClient(),
        login_url="https://portal.example.com/api/login",
    )
    r1 = await use_case.execute(LoginRequest(token="t1"))
    r2 = await use_case.execute(LoginRequest(token="t2"))
    assert r1.session_id != r2.session_id
