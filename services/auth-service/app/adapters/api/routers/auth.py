from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.application.dto.auth import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
from app.application.use_cases.login import LoginUseCase
from app.application.use_cases.refresh_token import RefreshTokenUseCase
from app.infrastructure.config import rate_limit
from app.infrastructure.config.database import get_db


def _client_ip(request: Request) -> str:
    """IP real de quien llama.

    Todo el trafico entra por Nginx, asi que `request.client.host` seria siempre la del
    gateway y el freno por IP no distinguiria a nadie. El gateway propaga la original en
    `X-Forwarded-For`; se toma el primer elemento, que es el cliente.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


router = APIRouter()


@router.post(
    "/api/v1/auth/login",
    response_model=LoginResponse,
    summary="Login de usuario",
    description=(
        "Autentica un usuario y devuelve access + refresh tokens JWT RS256.\n\n"
        "El tenant se resuelve en este orden de prioridad:\n"
        "1. Header `X-Tenant-Slug` (inyectado por Nginx cuando el request viene del subdomain).\n"
        "2. Campo `tenant_slug` en el body.\n"
        "3. Auto-deteccion por dominio del email si el tenant tiene `email_domain` configurado.\n\n"
        "**Limite de intentos:** tras varios fallos seguidos sobre el mismo correo o desde la "
        "misma IP el endpoint responde 429 durante unos minutos. Un login correcto borra el "
        "contador."
    ),
    response_description="Tokens JWT y metadata del tenant.",
    responses={
        400: {"description": "tenant_slug no proporcionado y no detectable."},
        401: {"description": "Credenciales incorrectas."},
        404: {"description": "Tenant no encontrado o inactivo."},
        429: {"description": "Demasiados intentos fallidos; reintentar mas tarde."},
    },
)
def login(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    x_tenant_slug: Optional[str] = Header(None, alias="X-Tenant-Slug"),
):
    client_ip = _client_ip(http_request)

    if rate_limit.is_locked(request.email, client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados intentos fallidos. Espere unos minutos antes de volver a " "intentarlo."
            ),
        )

    try:
        use_case = LoginUseCase(meta_db=db)
        response = use_case.execute(request, tenant_slug_header=x_tenant_slug)
    except ValueError as exc:
        msg = str(exc)
        if "credentials" in msg.lower():
            # Solo cuentan los fallos de contrasena. Un tenant inexistente o un payload
            # incompleto son errores de configuracion de quien integra, no un tanteo, y
            # penalizarlos bloquearia a un cliente nuevo mientras afina su llamada.
            rate_limit.register_failure(request.email, client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    rate_limit.clear(request.email, client_ip)
    return response


@router.post(
    "/api/v1/auth/refresh",
    response_model=RefreshResponse,
    summary="Renovar tokens",
    description=(
        "Intercambia un refresh token por un nuevo par access/refresh.\n\n"
        "El refresh token se invalida al usarse (rotacion). Si el token ya fue usado o ha expirado, retorna 401."
    ),
    response_description="Nuevos tokens JWT.",
    responses={
        401: {"description": "Refresh token invalido, expirado o ya usado."},
    },
)
def refresh(request: RefreshRequest):
    try:
        return RefreshTokenUseCase().execute(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
