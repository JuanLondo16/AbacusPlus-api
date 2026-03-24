from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ExternalClientPort(ABC):
    @abstractmethod
    async def login(
        self, login_url: str, credentials: Dict[str, Any]
    ) -> Dict[str, str]:
        """Autentica con el portal externo. Retorna cookies capturadas {nombre: valor}."""
        ...

    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        cookies: Dict[str, str],
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Reenvía una petición usando las cookies de sesión. Retorna {status_code, body, headers}."""
        ...

    @abstractmethod
    async def login_and_request(
        self,
        login_url: str,
        credentials: Dict[str, Any],
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Autentica y hace la petición en un único cliente para preservar las cookies."""
        ...
