import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import create_engine, NullPool, text

router = APIRouter()


def _verify_internal_secret(x_internal_secret: str = Header(...)):
    expected = os.environ.get("INTERNAL_SECRET", "")
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _migrate_tenant_db(engine) -> None:
    """Idempotent schema migrations. Safe to run on new or existing tenant DBs."""
    import app.infrastructure.persistence.models  # noqa: ensure all models are registered with Base
    from app.infrastructure.config.database import Base

    Base.metadata.create_all(bind=engine, checkfirst=True)

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO document_statuses (id, name) VALUES
                (0, 'Error'), (100, 'Procesado'), (200, 'Causado'),
                (300, 'Aprobado'), (400, 'Contabilizada')
            ON CONFLICT (id) DO NOTHING
        """))
        conn.execute(text("""
            DO $$
            BEGIN
                IF (SELECT data_type FROM information_schema.columns
                    WHERE table_name='documents' AND column_name='status') = 'character varying' THEN
                    ALTER TABLE documents ALTER COLUMN status TYPE INTEGER USING
                        CASE status
                            WHEN 'Procesado'      THEN 100
                            WHEN 'procesado'      THEN 100
                            WHEN 'processed'      THEN 100
                            WHEN 'Causado'        THEN 200
                            WHEN 'causado'        THEN 200
                            WHEN 'Aprobado'       THEN 300
                            WHEN 'aprobado'       THEN 300
                            WHEN 'Contabilizada'  THEN 400
                            WHEN 'contabilizada'  THEN 400
                            ELSE 0
                        END;
                END IF;
            END $$;
        """))
        conn.execute(text(
            "ALTER TABLE processing_logs "
            "ADD COLUMN IF NOT EXISTS xml_filename VARCHAR(255)"
        ))
        conn.execute(text(
            "ALTER TABLE processing_logs "
            "ADD COLUMN IF NOT EXISTS accounting_status VARCHAR(20)"
        ))
        conn.execute(text(
            "ALTER TABLE processing_logs "
            "ADD COLUMN IF NOT EXISTS accounting_error TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE documents "
            "ALTER COLUMN issuer_phone TYPE VARCHAR(100), "
            "ALTER COLUMN receiver_phone TYPE VARCHAR(100)"
        ))
        conn.execute(text(
            "ALTER TABLE issuers "
            "ADD COLUMN IF NOT EXISTS tipo_contribuyente VARCHAR(50)"
        ))
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
    return {"status": "provisioned", "tenant_slug": tenant_slug, "service": os.environ.get("SERVICE_NAME", "unknown")}
