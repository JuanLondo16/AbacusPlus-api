import uuid
import logging

from app.domain.entities.session import SessionEntity
from app.domain.ports.repositories import SessionStorePort
from app.infrastructure.browser.playwright_client import PlaywrightBrowserClient
from app.domain.exceptions.base import ExternalAuthException
from app.application.dto.company_login import CompanyLoginResponse

logger = logging.getLogger(__name__)


class CompanyLoginUseCase:
    def __init__(
        self,
        session_store: SessionStorePort,
        browser_client: PlaywrightBrowserClient,
        login_url: str,
    ):
        self._store = session_store
        self._client = browser_client
        self._login_url = login_url

    async def execute(self) -> CompanyLoginResponse:
        cookies, steps = await self._client.company_login(self._login_url)

        if not cookies:
            raise ExternalAuthException(
                "No se obtuvieron cookies del login por browser"
            )

        session_id = str(uuid.uuid4())
        self._store.save(SessionEntity(session_id=session_id, cookies=cookies))

        logger.info("Sesión creada por browser login: %s (%d cookies)", session_id, len(cookies))
        return CompanyLoginResponse(session_id=session_id, steps=steps)
