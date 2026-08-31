import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.chunks import router as chunks_router
from app.adapters.api.routers.internal import router as internal_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import chunk as _chunk_model  # noqa: F401
from app.infrastructure.persistence.tenant_migrations import run_tenant_migrations

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    internal_secret = os.environ.get("INTERNAL_SECRET", "")
    if not internal_secret or internal_secret == "change-me":
        raise RuntimeError(
            "INTERNAL_SECRET no está configurado (o sigue en 'change-me' de .env.example). "
            "Los endpoints /internal/* de todos los servicios lo requieren para autenticar "
            "llamadas entre microservicios. Genera uno real: openssl rand -hex 32"
        )
    Base.metadata.create_all(bind=engine, checkfirst=True)
    run_tenant_migrations(engine)
    logger.info("Tabla document_chunks verificada/creada")
    yield


app = FastAPI(
    title="RAG Service",
    description="Microservicio para indexación y búsqueda semántica de documentos con pgvector",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(chunks_router, prefix="/api/v1", tags=["chunks"])
app.include_router(internal_router)  # no prefix — path is /internal/provision-tenant

logger.info("RAG Service started on port 8002")


@app.get(
    "/health",
    summary="Health check del RAG Service",
    description="Verifica que el microservicio de embeddings y búsqueda semántica esté activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "rag-service"}
