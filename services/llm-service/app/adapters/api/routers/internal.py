import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import create_engine, NullPool, text

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
    _run_structural_migrations(engine)
    engine.dispose()
    return {"status": "provisioned", "tenant_slug": tenant_slug}


def _run_structural_migrations(engine) -> None:
    """Apply ADD COLUMN IF NOT EXISTS for columns that may be missing in older tenant DBs."""
    with engine.connect() as conn:
        # Odoo-origin columns in accounting_entries
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS name VARCHAR(100)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS date DATE"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS ref VARCHAR(200)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS move_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS state VARCHAR(20)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS journal_id INTEGER"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS journal_name VARCHAR(100)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS partner_id INTEGER"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS partner_name VARCHAR(200)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS partner_vat VARCHAR(50)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS currency_name VARCHAR(10)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS amount_untaxed NUMERIC(18,2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS amount_tax NUMERIC(18,2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS amount_total NUMERIC(18,2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS narration TEXT"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS batch_id VARCHAR(36)"))
        # LLM-origin columns
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS issuer_nit VARCHAR(20)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS issuer_name VARCHAR(200)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS system_prompt_id INTEGER"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS model_used VARCHAR(50)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS status VARCHAR(20)"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS error_message TEXT"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS rag_context JSON"))
        # Defaults and nullability fixes
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN source_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN amount_untaxed SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN amount_tax SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN amount_total SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN extracted_at SET DEFAULT NOW()"))
        # accounting_entry_lines extras
        conn.execute(text("ALTER TABLE accounting_entry_lines ADD COLUMN IF NOT EXISTS source_move_id INTEGER"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ADD COLUMN IF NOT EXISTS sequence INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ADD COLUMN IF NOT EXISTS amount_currency NUMERIC(18,2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ADD COLUMN IF NOT EXISTS date_maturity DATE"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMP NOT NULL DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN source_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN debit SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN credit SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN amount_currency SET DEFAULT 0"))
        conn.commit()
