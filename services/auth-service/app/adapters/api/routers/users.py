from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.user import InviteUserRequest, UserResponse
from app.application.use_cases.invite_user import InviteUserUseCase
from app.infrastructure.config.auth_dependency import TokenData, require_tenant_admin
from app.infrastructure.config.database import get_db
from app.infrastructure.config.tenant_connection import get_session_for_tenant
from app.infrastructure.persistence.repositories.user_repository import UserRepository

router = APIRouter()


@router.post(
    "/api/v1/users/invite",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invitar usuario al tenant",
    description=(
        "Crea un nuevo usuario dentro del tenant **del token de quien llama**.\n\n"
        "Requiere un access token con rol `tenant_admin`. El tenant NO se toma del header "
        "`X-Tenant-Slug`: se resuelve desde el token, de modo que un administrador solo puede "
        "crear usuarios dentro de su propia empresa.\n\n"
        "Roles disponibles: `tenant_admin`, `operator`, `viewer`."
    ),
    response_description="Datos del usuario creado.",
    responses={
        400: {"description": "Usuario ya existe o datos invalidos."},
        401: {"description": "Falta el token o no es valido."},
        403: {"description": "El usuario no es administrador del tenant."},
    },
)
def invite_user(
    request: InviteUserRequest,
    token: Annotated[TokenData, Depends(require_tenant_admin)],
    db: Session = Depends(get_db),
):
    try:
        use_case = InviteUserUseCase(meta_db=db)
        return use_case.execute(request, tenant_slug=token.tenant_slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/api/v1/users",
    response_model=list[UserResponse],
    summary="Listar usuarios del tenant",
    description=(
        "Retorna los usuarios activos del tenant **del token de quien llama**. "
        "Requiere rol `tenant_admin`: el listado expone los correos de toda la empresa."
    ),
    response_description="Lista de usuarios.",
    responses={
        401: {"description": "Falta el token o no es valido."},
        403: {"description": "El usuario no es administrador del tenant."},
    },
)
def list_users(token: Annotated[TokenData, Depends(require_tenant_admin)]):
    tenant_db = get_session_for_tenant(token.tenant_slug)
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
