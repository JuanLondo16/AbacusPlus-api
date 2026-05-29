from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.tenant import RegisterTenantRequest, TenantResponse
from app.application.use_cases.register_tenant import RegisterTenantUseCase
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
        "**Nota:** Este endpoint no requiere autenticacion para permitir el registro inicial. "
        "En produccion se recomienda protegerlo con una API key de bootstrap."
    ),
    response_description="Datos del tenant creado.",
    responses={
        400: {"description": "Slug invalido o tenant ya existe."},
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
    description="Retorna todos los tenants activos. Endpoint administrativo.",
    response_description="Lista de tenants activos.",
)
def list_tenants(db: Session = Depends(get_db)):
    repo = TenantRepository(db)
    tenants = repo.list_all()
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
