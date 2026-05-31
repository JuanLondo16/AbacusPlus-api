import pytest
from app.application.dto.proxy import ProxyRequest
from app.application.use_cases.proxy_request import ProxyRequestUseCase
from app.domain.ports.services import ExternalClientPort

_FAKE_RESPONSE = {"status_code": 200, "body": {"result": "ok"}, "headers": {}}


class FakeExternalClient(ExternalClientPort):
    def __init__(self, response: dict = None):
        self._response = response or _FAKE_RESPONSE
        self.last_call: dict = {}

    async def login(self, login_url, credentials):
        return {}

    async def request(self, method, url, cookies, body=None, params=None):
        # No sobreescribir campos capturados por login_and_request (ej: credentials)
        self.last_call.update({"method": method, "url": url, "cookies": cookies})
        return self._response

    async def login_and_request(
        self,
        login_url: str,
        credentials: dict,
        method: str,
        url: str,
        body=None,
        params=None,
    ) -> dict:
        self.last_call = {
            "login_url": login_url,
            "credentials": credentials,
            "method": method,
            "url": url,
            "body": body,
            "params": params,
        }
        cookies = await self.login(login_url=login_url, credentials=credentials)
        return await self.request(method=method, url=url, cookies=cookies, body=body, params=params)

    async def login_and_download(
        self, login_url: str, credentials: dict, download_url: str
    ) -> bytes:
        return b""


def _make_use_case(
    client=None,
    base_url="https://portal.example.com",
    login_url="https://portal.example.com/api/login",
):
    use_case = ProxyRequestUseCase(
        external_client=client or FakeExternalClient(),
        base_url=base_url,
        login_url=login_url,
    )
    return use_case


@pytest.mark.asyncio
async def test_returns_proxy_response():
    use_case = _make_use_case()
    result = await use_case.execute(ProxyRequest(token="mi-token", method="GET", path="/api/data"))
    assert result.status_code == 200
    assert result.body == {"result": "ok"}


@pytest.mark.asyncio
async def test_full_url_is_constructed_correctly():
    client = FakeExternalClient()
    use_case = _make_use_case(client=client, base_url="https://portal.example.com")
    await use_case.execute(ProxyRequest(token="mi-token", method="GET", path="/api/invoices"))
    assert client.last_call["url"] == "https://portal.example.com/api/invoices"


@pytest.mark.asyncio
async def test_token_is_passed_as_credentials():
    client = FakeExternalClient()
    use_case = _make_use_case(client=client, base_url="https://portal.example.com")
    await use_case.execute(
        ProxyRequest(token="mi-token", method="POST", path="/api/submit", body={"x": 1})
    )
    assert client.last_call["credentials"] == {"token": "mi-token"}
    assert client.last_call["method"] == "POST"
    assert client.last_call["url"] == "https://portal.example.com/api/submit"
    assert client.last_call["body"] == {"x": 1}
