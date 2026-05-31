import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions.base import DomainException

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "VALIDATION_ERROR": 400,
    "NOT_FOUND": 404,
    "ODOO_CONNECTION_ERROR": 502,
    "DOMAIN_ERROR": 500,
}


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_MAP.get(exc.code, 500),
        content={"error": exc.code, "detail": exc.message},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "detail": "An unexpected error occurred"},
    )
