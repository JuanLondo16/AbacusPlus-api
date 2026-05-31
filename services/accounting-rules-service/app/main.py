import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.internal import router as internal_router
from app.adapters.api.routers.lookups import router as lookups_router
from app.adapters.api.routers.rules import router as rules_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import accounting_rule as _ar_model  # noqa: F401
from app.infrastructure.persistence.models import rule_match_attempt as _rma_model  # noqa: F401

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Tablas accounting_rules y rule_match_attempts verificadas/creadas")
    yield


app = FastAPI(
    title="Accounting Rules Service",
    description=(
        "Microservicio de memoria estructurada de causaciones aprobadas.\n\n"
        "Aprende de cada aprobación de asiento contable (`PATCH /approve` en xml-processor) "
        "y provee causaciones sugeridas al `llm-service` antes de llamar al LLM de OpenAI, "
        "mejorando progresivamente la precisión sin necesidad de fine-tuning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(rules_router, prefix="/api/v1", tags=["rules"])
app.include_router(lookups_router, prefix="/api/v1", tags=["lookups"])
app.include_router(internal_router)

logger.info("Accounting Rules Service started on port 8009")


@app.get(
    "/health",
    summary="Health check del Accounting Rules Service",
    description="Verifica que el microservicio de reglas contables esté activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "accounting-rules-service"}
