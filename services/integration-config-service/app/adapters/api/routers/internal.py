import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import create_engine, NullPool

router = APIRouter()


def _verify_internal_secret(x_internal_secret: str = Header(...)):
    expected = os.environ.get("INTERNAL_SECRET", "")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post(
    "/internal/provision-tenant",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def provision_tenant(tenant_slug: str):
    """Create all tables for this service in the tenant DB. Called by auth-service during tenant registration."""
    import app.infrastructure.persistence.models  # noqa: ensure all models are registered with Base
    from app.infrastructure.config.database import Base

    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{tenant_slug}"
    engine = create_engine(url, poolclass=NullPool)
    Base.metadata.create_all(bind=engine, checkfirst=True)
    engine.dispose()
    return {"status": "provisioned", "tenant_slug": tenant_slug, "service": __import__("os").environ.get("SERVICE_NAME", "unknown")}
