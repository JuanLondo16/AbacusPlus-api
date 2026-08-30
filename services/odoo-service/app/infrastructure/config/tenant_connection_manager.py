import os
import re
import threading

from sqlalchemy import NullPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

_lock = threading.Lock()
_session_factories: dict[str, sessionmaker] = {}

# Formato que produce el aprovisionamiento de tenants: minúsculas, dígitos y guion bajo.
_SLUG_PATTERN = re.compile(r"[a-z0-9_]+")


def _validated_slug(tenant_slug: str) -> str:
    """Valida el slug antes de interpolarlo en la URL de conexión.

    El slug llega de un claim del JWT (o de una llamada interna). Aunque el token esté firmado,
    termina concatenado en un DSN, así que un valor con caracteres de sintaxis de URL podría
    alterar el destino de la conexión. Se restringe al formato del aprovisionamiento como
    defensa en profundidad.
    """
    if not _SLUG_PATTERN.fullmatch(tenant_slug or ""):
        raise ValueError(f"Slug de tenant inválido: {tenant_slug!r}")
    return tenant_slug


def _build_url(tenant_slug: str) -> str:
    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    slug = _validated_slug(tenant_slug)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{slug}"


def get_session_for_tenant(tenant_slug: str) -> Session:
    if tenant_slug not in _session_factories:
        with _lock:
            if tenant_slug not in _session_factories:
                engine = create_engine(_build_url(tenant_slug), poolclass=NullPool)
                _session_factories[tenant_slug] = sessionmaker(
                    autocommit=False, autoflush=False, bind=engine
                )
    return _session_factories[tenant_slug]()
