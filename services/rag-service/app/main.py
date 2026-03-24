import logging
from fastapi import FastAPI, HTTPException, status
from app.infrastructure.config.logging import setup_logging
from app.adapters.api.routers.chunks import router as chunks_router
from app.domain.exceptions.base import DomainException
from app.adapters.api.error_handlers import domain_exception_handler, unhandled_exception_handler

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Service",
    description="Microservicio para indexación y búsqueda semántica de documentos con pgvector",
    version="1.0.0",
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(chunks_router, prefix="/api/v1", tags=["chunks"])

logger.info("RAG Service started on port 8002")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "rag-service"}


@app.get("/{path:path}")
async def not_found(path: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route not found: {path}")
