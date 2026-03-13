import logging
from fastapi import FastAPI, HTTPException, status
from app.infrastructure.config.logging import setup_logging
from app.adapters.api.routers.xml import router as xml_router
from app.adapters.api.routers.documents import router as documents_router
from app.adapters.api.routers.receivers import router as receivers_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import (
    domain_exception_handler,
    unhandled_exception_handler,
)

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="XML Reader API",
    description="API for processing XML and ZIP files",
    version="1.0.0",
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(xml_router, prefix="/api/v1", tags=["xml"])
app.include_router(documents_router, prefix="/api/v1", tags=["documents"])
app.include_router(receivers_router, prefix="/api/v1", tags=["receivers"])

logger.info("XML Reader API started")


@app.get("/")
async def read_root():
    return {"message": "Welcome to the XML Processing API"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/{path:path}")
async def not_found(path: str):
    """Handles routes not found."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Route not found: {path}",
    )
