from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.auth import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
from app.application.use_cases.login import LoginUseCase
from app.application.use_cases.refresh_token import RefreshTokenUseCase
from app.infrastructure.config.database import get_db

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
        "3. Auto-deteccion por dominio del email si el tenant tiene `email_domain` configurado."
    ),
    response_description="Tokens JWT y metadata del tenant.",
    responses={
        400: {"description": "tenant_slug no proporcionado y no detectable."},
        401: {"description": "Credenciales incorrectas."},
        404: {"description": "Tenant no encontrado o inactivo."},
    },
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    x_tenant_slug: Optional[str] = Header(None, alias="X-Tenant-Slug"),
):
    try:
        use_case = LoginUseCase(meta_db=db)
        return use_case.execute(request, tenant_slug_header=x_tenant_slug)
    except ValueError as exc:
        msg = str(exc)
        if "credentials" in msg.lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


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
