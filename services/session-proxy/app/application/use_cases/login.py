import logging
import uuid

from app.application.dto.auth import LoginRequest, LoginResponse
from app.domain.entities.session import SessionEntity
from app.domain.exceptions.base import ExternalAuthException
from app.domain.ports.repositories import SessionStorePort
from app.domain.ports.services import ExternalClientPort

logger = logging.getLogger(__name__)


class LoginUseCase:
    def __init__(
        self,
        session_store: SessionStorePort,
        external_client: ExternalClientPort,
        login_url: str,
    ):
        self._store = session_store
        self._client = external_client
        self._login_url = login_url

    async def execute(self, request: LoginRequest) -> LoginResponse:
        cookies = await self._client.login(
            login_url=self._login_url,
            credentials={"token": request.token, "pk": request.pk, "rk": request.rk},
        )

        if not cookies:
            raise ExternalAuthException("El portal externo no retornó cookies de sesión")

        session_id = str(uuid.uuid4())
        session = SessionEntity(session_id=session_id, cookies=cookies)
        self._store.save(session)

        logger.info("Sesión creada: %s (%d cookies)", session_id, len(cookies))
        return LoginResponse(session_id=session_id)
