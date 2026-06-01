import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import NullPool, create_engine, text

router = APIRouter()


def _verify_internal_secret(x_internal_secret: str = Header(...)):
    expected = os.environ.get("INTERNAL_SECRET", "")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _migrate_tenant_db(engine) -> None:
    """Idempotent schema migrations. Safe to run on new or existing tenant DBs."""
    from app.infrastructure.config.database import Base

    Base.metadata.create_all(bind=engine, checkfirst=True)

    with engine.connect() as conn:
        # Eliminar provider y account_key de integration_cost_centers (simplificación)
        conn.execute(text("ALTER TABLE integration_cost_centers DROP COLUMN IF EXISTS provider"))
        conn.execute(text("ALTER TABLE integration_cost_centers DROP COLUMN IF EXISTS account_key"))
        conn.execute(
            text(
                "ALTER TABLE integration_cost_centers "
                "DROP CONSTRAINT IF EXISTS uq_cost_center_provider_key_code"
            )
        )
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cost_center_code') "
                "THEN ALTER TABLE integration_cost_centers ADD CONSTRAINT uq_cost_center_code UNIQUE (code); "
                "END IF; END $$"
            )
        )
        conn.commit()


@router.post(
    "/internal/provision-tenant",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def provision_tenant(tenant_slug: str):
    """Create/migrate all tables for this service in the tenant DB. Safe to re-run on existing tenants."""
    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{tenant_slug}"
    engine = create_engine(url, poolclass=NullPool)
    _migrate_tenant_db(engine)
    engine.dispose()
    return {
        "status": "provisioned",
        "tenant_slug": tenant_slug,
        "service": os.environ.get("SERVICE_NAME", "unknown"),
    }
