import logging

from app.domain.ports.services import ExternalClientPort
from app.application.dto.proxy import ProxyRequest, ProxyResponse

logger = logging.getLogger(__name__)


class ProxyRequestUseCase:
    def __init__(
        self,
        external_client: ExternalClientPort,
        base_url: str,
        login_url: str,
    ):
        self._client = external_client
        self._base_url = base_url.rstrip("/")
        self._login_url = login_url

    async def execute(self, request: ProxyRequest) -> ProxyResponse:
        full_url = f"{self._base_url}{request.path}"
        logger.info("Proxy: %s %s", request.method.upper(), full_url)

        result = await self._client.login_and_request(
            login_url=self._login_url,
            credentials={"token": request.token},
            method=request.method.upper(),
            url=full_url,
            body=request.body,
            params=request.params,
        )

        return ProxyResponse(
            status_code=result["status_code"],
            body=result["body"],
            headers=result.get("headers", {}),
            request_body=result.get("request_body"),
        )
