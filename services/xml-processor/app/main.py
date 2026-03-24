import logging
from fastapi import FastAPI, HTTPException, status
from app.infrastructure.config.logging import setup_logging
from app.adapters.api.routers.xml import router as xml_router
from app.adapters.api.routers.documents import router as documents_router
from app.adapters.api.routers.receivers import router as receivers_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="XML Processor Service",
    description="Microservicio para procesar facturas DIAN en formato XML/ZIP",
    version="1.0.0",
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(xml_router, prefix="/api/v1", tags=["xml"])
app.include_router(documents_router, prefix="/api/v1", tags=["documents"])
app.include_router(receivers_router, prefix="/api/v1", tags=["receivers"])

logger.info("XML Processor Service started on port 8001")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "xml-processor"}


@app.get("/{path:path}")
async def not_found(path: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route not found: {path}")
