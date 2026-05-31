import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.accounting import router as accounting_router
from app.adapters.api.routers.analyze import router as analyze_router
from app.adapters.api.routers.internal import router as internal_router
from app.adapters.api.routers.query import router as query_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, SessionLocal, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import accounting_entry as _ae_model  # noqa: F401
from app.infrastructure.persistence.models import chart_account as _ca_model  # noqa: F401
from app.infrastructure.persistence.models import system_prompt as _sp_model  # noqa: F401
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

setup_logging()
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    with engine.connect() as conn:
        # Columnas LLM en accounting_entries
        conn.execute(
            text(
                "ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS source VARCHAR(10) DEFAULT 'odoo'"
            )
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS issuer_nit VARCHAR(20)")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS issuer_name VARCHAR(200)")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS system_prompt_id INTEGER")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS model_used VARCHAR(50)")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS status VARCHAR(20)")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS error_message TEXT")
        )
        conn.execute(
            text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS rag_context JSON")
        )
        # source_id nullable para entradas LLM
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN source_id DROP NOT NULL"))
        conn.execute(
            text("ALTER TABLE accounting_entry_lines ALTER COLUMN source_id DROP NOT NULL")
        )
        # DB-level defaults para columnas NOT NULL que el llm-service no provee
        conn.execute(
            text("ALTER TABLE accounting_entries ALTER COLUMN amount_untaxed SET DEFAULT 0")
        )
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN amount_tax SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN amount_total SET DEFAULT 0"))
        conn.execute(
            text("ALTER TABLE accounting_entries ALTER COLUMN extracted_at SET DEFAULT NOW()")
        )
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN sequence SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN debit SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN credit SET DEFAULT 0"))
        conn.execute(
            text("ALTER TABLE accounting_entry_lines ALTER COLUMN amount_currency SET DEFAULT 0")
        )
        conn.execute(
            text("ALTER TABLE accounting_entry_lines ALTER COLUMN extracted_at SET DEFAULT NOW()")
        )
        conn.commit()
    logger.info("Migraciones estructurales completadas")


def _migrate_generated_tables() -> None:
    """Migra datos de generated_* a accounting_* y elimina las tablas viejas."""
    with engine.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generated_accounting_entries')"
            )
        ).scalar()
        if not exists:
            return

        count = conn.execute(text("SELECT COUNT(*) FROM generated_accounting_entries")).scalar()
        if count == 0:
            conn.execute(text("DROP TABLE IF EXISTS generated_accounting_entry_lines CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS generated_accounting_entries CASCADE"))
            conn.commit()
            return

        logger.info(
            "Migrando %d registros de generated_accounting_entries → accounting_entries", count
        )
        conn.execute(
            text("""
            INSERT INTO accounting_entries
                (source, issuer_nit, issuer_name, system_prompt_id, model_used,
                 status, error_message, rag_context, extracted_at,
                 amount_untaxed, amount_tax, amount_total)
            SELECT
                'llm', issuer_nit, issuer_name, system_prompt_id, model_used,
                status, error_message, rag_context, created_at,
                0, 0, 0
            FROM generated_accounting_entries g
            WHERE NOT EXISTS (
                SELECT 1 FROM accounting_entries ae
                WHERE ae.source = 'llm'
                  AND ae.extracted_at = g.created_at
                  AND ae.issuer_nit IS NOT DISTINCT FROM g.issuer_nit
                  AND ae.model_used IS NOT DISTINCT FROM g.model_used
            )
        """)
        )
        conn.commit()

        conn.execute(
            text("""
            INSERT INTO accounting_entry_lines
                (entry_id, account_code, account_name, debit, credit,
                 partner_name, cost_center, name, sequence, amount_currency, extracted_at)
            SELECT
                ae_new.id,
                gel.cuenta, gel.nombre,
                gel.debito, gel.credito,
                gel.tercero, gel.centro_costo, gel.descripcion,
                0, 0, NOW()
            FROM generated_accounting_entry_lines gel
            JOIN generated_accounting_entries gae ON gae.id = gel.entry_id
            JOIN accounting_entries ae_new
                ON ae_new.source = 'llm'
               AND ae_new.extracted_at = gae.created_at
               AND ae_new.issuer_nit IS NOT DISTINCT FROM gae.issuer_nit
               AND ae_new.model_used IS NOT DISTINCT FROM gae.model_used
            WHERE NOT EXISTS (
                SELECT 1 FROM accounting_entry_lines ael WHERE ael.entry_id = ae_new.id
            )
        """)
        )
        conn.commit()

        conn.execute(text("DROP TABLE IF EXISTS generated_accounting_entry_lines CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS generated_accounting_entries CASCADE"))
        conn.commit()
        logger.info("Migración completada — tablas generated_* eliminadas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    _migrate_generated_tables()
    db = SessionLocal()
    try:
        SystemPromptRepository(db).create_default_if_none()
    finally:
        db.close()
    logger.info("LLM Service listo")
    yield


app = FastAPI(
    title="LLM Service",
    description="Microservicio de orquestación LLM con soporte RAG via OpenAI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(analyze_router, prefix="/api/v1", tags=["analyze"])
app.include_router(query_router, prefix="/api/v1", tags=["query"])
app.include_router(accounting_router, prefix="/api/v1", tags=["accounting"])
app.include_router(internal_router)  # no prefix — path is /internal/provision-tenant

logger.info("LLM Service started on port 8003")


@app.get(
    "/health",
    summary="Health check del LLM Service",
    description="Verifica que el microservicio de orquestación LLM esté activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "llm-service"}
