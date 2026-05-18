import logging

from fastapi import FastAPI, HTTPException, status

from app.infrastructure.config.logging import setup_logging
from app.adapters.api.routers.auth import router as auth_router
from app.adapters.api.routers.proxy import router as proxy_router
from app.adapters.api.routers.documents import router as documents_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Session Proxy Service",
    description="Microservicio proxy de sesiones para portales externos con autenticación por cookies",
    version="1.0.0",
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(proxy_router, prefix="/api/v1", tags=["proxy"])
app.include_router(documents_router, prefix="/api/v1", tags=["documents"])

logger.info("Session Proxy Service iniciado en puerto 8004")


@app.get(
    "/health",
    summary="Health check del Session Proxy",
    description="Verifica que el microservicio de sesiones y descargas DIAN esté activo.",
    response_description="Estado operativo del servicio.",
)
async def health_check():
    return {"status": "healthy", "service": "session-proxy"}


@app.get(
    "/{path:path}",
    summary="Ruta no encontrada",
    description="Responde `404` para cualquier ruta no definida por el Session Proxy.",
    include_in_schema=False,
)
async def not_found(path: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route not found: {path}")
