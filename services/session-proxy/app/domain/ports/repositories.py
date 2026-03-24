from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities.session import SessionEntity


class SessionStorePort(ABC):
    @abstractmethod
    def save(self, session: SessionEntity) -> None: ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[SessionEntity]: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...
