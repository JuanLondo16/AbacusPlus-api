import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.accounting import router as accounting_router
from app.adapters.api.routers.analyze import router as analyze_router
from app.adapters.api.routers.internal import router as internal_router
from app.adapters.api.routers.query import router as query_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.clients.http_pool import close_client
from app.infrastructure.config.database import Base, SessionLocal, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import chart_account as _ca_model  # noqa: F401
from app.infrastructure.persistence.models import system_prompt as _sp_model  # noqa: F401
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    db = SessionLocal()
    try:
        SystemPromptRepository(db).create_default_if_none()
    finally:
        db.close()
    logger.info("LLM Service listo")
    yield
    # El pool HTTP compartido sobrevive a las peticiones, así que hay que cerrarlo aquí: sin
    # esto, apagar el servicio dejaría conexiones abiertas contra el resto de microservicios.
    await close_client()


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
