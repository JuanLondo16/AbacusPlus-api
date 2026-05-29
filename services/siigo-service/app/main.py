import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.chart_accounts import router as chart_accounts_router
from app.adapters.api.routers.credentials import router as credentials_router
from app.adapters.api.routers.journal_entries import router as journal_entries_router
from app.adapters.api.routers.purchase_invoice_parameters import router as purchase_invoice_parameters_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import chart_account as _chart_account_model  # noqa: F401
from app.infrastructure.persistence.models import integration as _integration_model  # noqa: F401
from app.infrastructure.persistence.models import purchase_invoice_parameter as _purchase_param_model  # noqa: F401
from app.adapters.api.routers.internal import router as internal_router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Tablas de siigo-service verificadas/creadas")
    yield


app = FastAPI(
    title="SIIGO Service",
    description=(
        "Microservicio para conectar AbacusPlus con SIIGO Nube.\n\n"
        "Consume credenciales y parametros administrados por integration-config-service, "
        "autentica contra SIIGO y sincroniza el plan de cuentas hacia PostgreSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(credentials_router, prefix="/api/v1", tags=["siigo"])
app.include_router(chart_accounts_router, prefix="/api/v1", tags=["siigo"])
app.include_router(purchase_invoice_parameters_router, prefix="/api/v1", tags=["siigo"])
app.include_router(journal_entries_router, prefix="/api/v1", tags=["siigo"])
app.include_router(internal_router)  # no prefix — path is /internal/provision-tenant

logger.info("SIIGO Service started on port 8006")


@app.get(
    "/health",
    summary="Health check del SIIGO Service",
    description="Verifica que el microservicio de conexion con SIIGO este activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "siigo-service"}
