import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from sqlalchemy import text

from app.infrastructure.config.logging import setup_logging
from app.infrastructure.config.database import Base, engine
from app.infrastructure.persistence.models import document, issuer, receiver, tax, concept, processing_log  # noqa: F401
from app.infrastructure.persistence.models import puc, retention_ica, retention_fuente, cost_center  # noqa: F401
from app.infrastructure.queue.download_queue import process_queue_worker
from app.adapters.api.routers.xml import router as xml_router
from app.adapters.api.routers.documents import router as documents_router
from app.adapters.api.routers.receivers import router as receivers_router
from app.adapters.api.routers.issuers import router as issuers_router
from app.adapters.api.routers.catalog import router as catalog_router
from app.adapters.api.routers.batch import router as batch_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    with engine.connect() as conn:
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
    logger.info("Tablas verificadas/creadas")
    task = asyncio.create_task(process_queue_worker())
    logger.info("Worker de cola iniciado")
    yield
    task.cancel()
    logger.info("Worker de cola detenido")


app = FastAPI(
    title="XML Processor Service",
    description="Microservicio para procesar facturas DIAN en formato XML/ZIP",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(xml_router, prefix="/api/v1", tags=["xml"])
app.include_router(documents_router, prefix="/api/v1", tags=["documents"])
app.include_router(receivers_router, prefix="/api/v1", tags=["receivers"])
app.include_router(issuers_router, prefix="/api/v1", tags=["issuers"])
app.include_router(catalog_router, prefix="/api/v1", tags=["catalog"])
app.include_router(batch_router, prefix="/api/v1", tags=["batch"])

logger.info("XML Processor Service started on port 8001")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "xml-processor"}


@app.get("/{path:path}")
async def not_found(path: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route not found: {path}")
