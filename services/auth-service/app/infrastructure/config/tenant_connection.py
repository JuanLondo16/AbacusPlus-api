import os
import threading
from typing import Dict

from sqlalchemy import create_engine, NullPool
from sqlalchemy.orm import sessionmaker, Session

_lock = threading.Lock()
_session_factories: Dict[str, sessionmaker] = {}


def _build_url(tenant_slug: str) -> str:
    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{tenant_slug}"


def get_session_for_tenant(tenant_slug: str) -> Session:
    if tenant_slug not in _session_factories:
        with _lock:
            if tenant_slug not in _session_factories:
                engine = create_engine(_build_url(tenant_slug), poolclass=NullPool)
                _session_factories[tenant_slug] = sessionmaker(
                    autocommit=False, autoflush=False, bind=engine
                )
    return _session_factories[tenant_slug]()
