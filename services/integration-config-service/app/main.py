import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler
from app.adapters.api.routers.chart_accounts import router as chart_accounts_router
from app.adapters.api.routers.cost_centers import router as cost_centers_router
from app.adapters.api.routers.credentials import router as credentials_router
from app.adapters.api.routers.purchase_invoice_parameters import router as purchase_invoice_parameters_router
from app.domain.exceptions.base import DomainException
from app.infrastructure.config.database import Base, engine
from app.infrastructure.config.logging import setup_logging
from app.infrastructure.persistence.models import chart_account as _chart_account_model  # noqa: F401
from app.infrastructure.persistence.models import cost_center as _cost_center_model  # noqa: F401
from app.infrastructure.persistence.models import integration as _integration_model  # noqa: F401
from app.infrastructure.persistence.models import purchase_invoice_parameter as _purchase_param_model  # noqa: F401

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Tablas de integration-config-service verificadas/creadas")
    yield


app = FastAPI(
    title="Integration Config Service",
    description=(
        "Microservicio central para parametrizar integraciones externas.\n\n"
        "Administra credenciales y parametros reutilizables por proveedor, de modo que "
        "los adaptadores como SIIGO consuman configuracion sin ser responsables de crearla."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(chart_accounts_router, prefix="/api/v1", tags=["integrations"])
app.include_router(cost_centers_router, prefix="/api/v1", tags=["integrations"])
app.include_router(credentials_router, prefix="/api/v1", tags=["integrations"])
app.include_router(purchase_invoice_parameters_router, prefix="/api/v1", tags=["integrations"])

logger.info("Integration Config Service started on port 8007")


@app.get(
    "/health",
    summary="Health check del Integration Config Service",
    description="Verifica que el microservicio de configuracion de integraciones este activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "integration-config-service"}


@app.get(
    "/{path:path}",
    summary="Ruta no encontrada",
    description="Responde `404` para cualquier ruta no definida por este servicio.",
    include_in_schema=False,
)
async def not_found(path: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route not found: {path}")
