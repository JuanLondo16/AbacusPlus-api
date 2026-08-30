from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.tenant import RegisterTenantRequest, TenantResponse
from app.application.use_cases.register_tenant import RegisterTenantUseCase
from app.infrastructure.config.auth_dependency import (
    TokenData,
    get_token_data,
    require_bootstrap_secret,
)
from app.infrastructure.config.database import get_db
from app.infrastructure.persistence.repositories.tenant_repository import TenantRepository

router = APIRouter()


@router.post(
    "/api/v1/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo tenant",
    description=(
        "Crea un nuevo tenant (empresa):\n"
        "1. Valida el slug (minusculas, alphanumerico, 2-31 chars).\n"
        "2. Crea la base de datos `abacus_t_{slug}` con la extension pgvector.\n"
        "3. Llama a cada microservicio para crear sus tablas en la nueva DB.\n"
        "4. Crea el usuario administrador inicial dentro de la DB del tenant.\n"
        "5. Registra el tenant en `abacus_meta`.\n\n"
        "**Autorizacion:** requiere el header `X-Internal-Secret` con el valor de "
        "`INTERNAL_SECRET`. No puede exigir un usuario autenticado porque el primer "
        "administrador del tenant nace de esta misma llamada; el secreto compartido es la "
        "barrera que impide que un tercero provoque la creacion ilimitada de bases de datos."
    ),
    response_description="Datos del tenant creado.",
    dependencies=[Depends(require_bootstrap_secret)],
    responses={
        400: {"description": "Slug invalido o tenant ya existe."},
        403: {"description": "Falta el secreto de bootstrap o no coincide."},
        500: {"description": "Error al provisionar la DB o los servicios."},
    },
)
def register_tenant(request: RegisterTenantRequest, db: Session = Depends(get_db)):
    try:
        use_case = RegisterTenantUseCase(meta_db=db)
        return use_case.execute(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/api/v1/tenants",
    response_model=list[TenantResponse],
    summary="Listar tenants",
    description=(
        "Retorna los datos del tenant al que pertenece el token. Endpoint administrativo.\n\n"
        "Antes devolvia la lista completa de clientes sin pedir token, lo que exponia la "
        "cartera de empresas de la plataforma a cualquiera. Cada usuario ve unicamente el "
        "suyo, que es el unico dato que la aplicacion necesita de aqui."
    ),
    response_description="Tenant del usuario autenticado.",
    responses={401: {"description": "Falta el token o no es valido."}},
)
def list_tenants(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_db),
):
    repo = TenantRepository(db)
    tenant = repo.get_by_slug(token.tenant_slug)
    tenants = [tenant] if tenant is not None else []
    return [
        TenantResponse(
            id=str(t.id),
            slug=t.slug,
            display_name=t.display_name,
            email_domain=t.email_domain,
            is_active=t.is_active,
        )
        for t in tenants
    ]
