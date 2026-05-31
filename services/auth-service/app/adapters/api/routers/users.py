from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.user import InviteUserRequest, UserResponse
from app.application.use_cases.invite_user import InviteUserUseCase
from app.infrastructure.config.database import get_db
from app.infrastructure.config.tenant_connection import get_session_for_tenant
from app.infrastructure.persistence.repositories.user_repository import UserRepository

router = APIRouter()


def _require_tenant_slug(x_tenant_slug: Optional[str] = Header(None, alias="X-Tenant-Slug")) -> str:
    if not x_tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-Slug header required"
        )
    return x_tenant_slug


@router.post(
    "/api/v1/users/invite",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invitar usuario al tenant",
    description=(
        "Crea un nuevo usuario dentro del tenant identificado por el header `X-Tenant-Slug`.\n\n"
        "Roles disponibles: `tenant_admin`, `operator`, `viewer`."
    ),
    response_description="Datos del usuario creado.",
    responses={
        400: {"description": "Usuario ya existe o datos invalidos."},
    },
)
def invite_user(
    request: InviteUserRequest,
    db: Session = Depends(get_db),
    tenant_slug: str = Depends(_require_tenant_slug),
):
    try:
        use_case = InviteUserUseCase(meta_db=db)
        return use_case.execute(request, tenant_slug=tenant_slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/api/v1/users",
    response_model=list[UserResponse],
    summary="Listar usuarios del tenant",
    description="Retorna todos los usuarios activos del tenant identificado por `X-Tenant-Slug`.",
    response_description="Lista de usuarios.",
)
def list_users(tenant_slug: str = Depends(_require_tenant_slug)):
    tenant_db = get_session_for_tenant(tenant_slug)
    try:
        repo = UserRepository(tenant_db)
        users = repo.list_users()
        result = []
        for u in users:
            roles = repo.get_roles(u.id)
            result.append(
                UserResponse(
                    id=str(u.id),
                    email=u.email,
                    full_name=u.full_name,
                    is_active=u.is_active,
                    roles=roles,
                )
            )
        return result
    finally:
        tenant_db.close()
