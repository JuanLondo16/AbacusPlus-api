import bcrypt
from sqlalchemy.orm import Session

from app.application.dto.tenant import RegisterTenantRequest, TenantResponse
from app.infrastructure.persistence.repositories.tenant_repository import TenantRepository
from app.infrastructure.provisioning import tenant_provisioner


class RegisterTenantUseCase:
    def __init__(self, meta_db: Session):
        self._meta_db = meta_db

    def execute(self, request: RegisterTenantRequest) -> TenantResponse:
        tenant_provisioner.validate_slug(request.slug)

        repo = TenantRepository(self._meta_db)
        if repo.get_by_slug(request.slug) is not None:
            raise ValueError(f"Tenant '{request.slug}' already exists")

        password_hash = bcrypt.hashpw(request.admin_password.encode(), bcrypt.gensalt()).decode()

        tenant_provisioner.provision(
            tenant_slug=request.slug,
            admin_email=request.admin_email,
            admin_password_hash=password_hash,
        )

        tenant = repo.create(
            slug=request.slug,
            display_name=request.display_name,
            email_domain=request.email_domain,
        )

        return TenantResponse(
            id=str(tenant.id),
            slug=tenant.slug,
            display_name=tenant.display_name,
            email_domain=tenant.email_domain,
            is_active=tenant.is_active,
        )
