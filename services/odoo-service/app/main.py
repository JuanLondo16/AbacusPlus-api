import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.internal import router as internal_router
from app.adapters.api.routers.journal_entries import router as journal_entries_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import accounting_entry as _ae_model  # noqa: F401

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text

    internal_secret = os.environ.get("INTERNAL_SECRET", "")
    if not internal_secret or internal_secret == "change-me":
        raise RuntimeError(
            "INTERNAL_SECRET no está configurado (o sigue en 'change-me' de .env.example). "
            "Los endpoints /internal/* de todos los servicios lo requieren para autenticar "
            "llamadas entre microservicios. Genera uno real: openssl rand -hex 32"
        )
    Base.metadata.create_all(bind=engine, checkfirst=True)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE accounting_entries ALTER COLUMN source_id DROP NOT NULL"))
        conn.execute(
            text(
                "ALTER TABLE accounting_entries ADD COLUMN IF NOT EXISTS source VARCHAR(10) DEFAULT 'odoo'"
            )
        )
        conn.execute(
            text("ALTER TABLE accounting_entry_lines ALTER COLUMN source_id DROP NOT NULL")
        )
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
