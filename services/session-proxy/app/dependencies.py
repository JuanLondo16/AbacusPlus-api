import os

from dotenv import load_dotenv

from app.infrastructure.session.in_memory_store import InMemorySessionStore
from app.infrastructure.clients.external_client import HttpxExternalClient
from app.application.use_cases.login import LoginUseCase
from app.application.use_cases.proxy_request import ProxyRequestUseCase

load_dotenv()

# Singleton: se crea una sola vez al importar este módulo.
# Todos los request handlers comparten esta instancia.
_SESSION_STORE = InMemorySessionStore(
    ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "3600"))
)


def get_session_store() -> InMemorySessionStore:
    return _SESSION_STORE


def get_external_client() -> HttpxExternalClient:
    return HttpxExternalClient(timeout=15.0)


def _build_login_url() -> str:
    base = os.getenv("EXTERNAL_BASE_URL", "https://portal.example.com").rstrip("/")
    path = os.getenv("EXTERNAL_LOGIN_PATH", "/api/login")
    return f"{base}{path}"


def get_login_use_case() -> LoginUseCase:
    return LoginUseCase(
        session_store=get_session_store(),
        external_client=get_external_client(),
        login_url=_build_login_url(),
    )


def get_proxy_request_use_case() -> ProxyRequestUseCase:
    return ProxyRequestUseCase(
        session_store=get_session_store(),
        external_client=get_external_client(),
        base_url=os.getenv("EXTERNAL_BASE_URL", "https://portal.example.com"),
    )
