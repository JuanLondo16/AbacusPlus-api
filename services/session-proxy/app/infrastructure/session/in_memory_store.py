import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from app.domain.entities.session import SessionEntity
from app.domain.ports.repositories import SessionStorePort

logger = logging.getLogger(__name__)


class InMemorySessionStore(SessionStorePort):
    """
    Store de sesiones en memoria con TTL sliding y evicción lazy.

    - TTL sliding: last_accessed_at se resetea en cada get() exitoso.
    - Evicción lazy: las sesiones expiradas se eliminan al accederse, sin hilo de fondo.
    - threading.Lock garantiza thread-safety entre workers de uvicorn.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = timedelta(seconds=ttl_seconds)
        self._store: dict[str, SessionEntity] = {}
        self._lock = threading.Lock()

    def save(self, session: SessionEntity) -> None:
        with self._lock:
            session.last_accessed_at = datetime.utcnow()
            self._store[session.session_id] = session

    def get(self, session_id: str) -> Optional[SessionEntity]:
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                del self._store[session_id]
                logger.info("Sesión eviccionada por TTL: %s", session_id)
                return None
            session.last_accessed_at = datetime.utcnow()
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
            logger.info("Sesión eliminada: %s", session_id)

    def _is_expired(self, session: SessionEntity) -> bool:
        return datetime.utcnow() - session.last_accessed_at > self._ttl
