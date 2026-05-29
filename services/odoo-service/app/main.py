import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.config.database import Base, engine
from app.infrastructure.persistence.models import accounting_entry as _ae_model  # noqa: F401
from app.adapters.api.routers.journal_entries import router as journal_entries_router
from app.adapters.api.routers.internal import router as internal_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine, checkfirst=True)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN source_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS source VARCHAR(10) DEFAULT 'odoo'"))
        conn.execute(text("ALTER TABLE accounting_entry_lines ALTER COLUMN source_id DROP NOT NULL"))
        conn.commit()
    logger.info("Tablas de odoo-service verificadas/creadas")
    yield


app = FastAPI(
    title="Odoo Service",
    description=(
        "Microservicio para extraer y almacenar asientos contables de compra desde Odoo.\n\n"
        "Se conecta vía XML-RPC y persiste los asientos en PostgreSQL como historial "
        "inmutable de causación de documentos contables."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(journal_entries_router, prefix="/api/v1", tags=["odoo"])
app.include_router(internal_router)  # no prefix — path is /internal/provision-tenant

logger.info("Odoo Service started on port 8005")


@app.get(
    "/health",
    summary="Health check del Odoo Service",
    description="Verifica que el microservicio de sincronización con Odoo esté activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "odoo-service"}
