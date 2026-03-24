import logging

from app.domain.ports.repositories import SessionStorePort
from app.domain.ports.services import ExternalClientPort
from app.domain.exceptions.base import SessionNotFoundException
from app.application.dto.proxy import ProxyRequest, ProxyResponse

logger = logging.getLogger(__name__)


class ProxyRequestUseCase:
    def __init__(
        self,
        session_store: SessionStorePort,
        external_client: ExternalClientPort,
        base_url: str,
    ):
        self._store = session_store
        self._client = external_client
        self._base_url = base_url.rstrip("/")

    async def execute(self, request: ProxyRequest) -> ProxyResponse:
        session = self._store.get(request.session_id)
        if session is None:
            raise SessionNotFoundException(request.session_id)

        full_url = f"{self._base_url}{request.path}"
        logger.info(
            "Proxy: %s %s (session=%s)", request.method.upper(), full_url, request.session_id
        )

        result = await self._client.request(
            method=request.method.upper(),
            url=full_url,
            cookies=session.cookies,
            body=request.body,
            params=request.params,
        )

        # Elimina la sesión para evitar cache del servidor en próximas peticiones
        self._store.delete(request.session_id)

        return ProxyResponse(
            status_code=result["status_code"],
            body=result["body"],
            headers=result.get("headers", {}),
            request_body=result.get("request_body"),
        )
