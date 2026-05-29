import bcrypt
from sqlalchemy.orm import Session

from app.application.dto.auth import LoginRequest, LoginResponse
from app.infrastructure.config import jwt as jwt_service
from app.infrastructure.config.redis_client import store_refresh_token
from app.infrastructure.config.tenant_connection import get_session_for_tenant
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.repositories.tenant_repository import TenantRepository
from app.infrastructure.persistence.repositories.user_repository import UserRepository


class LoginUseCase:
    def __init__(self, meta_db: Session):
        self._meta_db = meta_db

    def execute(self, request: LoginRequest, tenant_slug_header: str | None) -> LoginResponse:
        tenant_slug = self._resolve_slug(request, tenant_slug_header)

        tenant_repo = TenantRepository(self._meta_db)
        tenant = tenant_repo.get_by_slug(tenant_slug)
        if tenant is None:
            raise ValueError("Tenant not found or inactive")

        tenant_db = get_session_for_tenant(tenant_slug)
        try:
            user_repo = UserRepository(tenant_db)
            user = user_repo.get_by_email(request.email)
            if user is None or not bcrypt.checkpw(request.password.encode(), user.password_hash.encode()):
                raise ValueError("Invalid credentials")

            roles = user_repo.get_roles(user.id)
        finally:
            tenant_db.close()

        access_token = jwt_service.issue_access_token(
            str(user.id), str(tenant.id), tenant.slug, user.email, roles
        )
        refresh_token, jti = jwt_service.issue_refresh_token(str(user.id), str(tenant.id), tenant.slug)

        expire_days = 7
        store_refresh_token(jti, str(user.id), expire_days)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            tenant_slug=tenant.slug,
            roles=roles,
        )

    def _resolve_slug(self, request: LoginRequest, header_slug: str | None) -> str:
        if header_slug:
            return header_slug
        if request.tenant_slug:
            return request.tenant_slug
        # Auto-detect by email domain
        domain = request.email.split("@")[-1]
        tenant = TenantRepository(self._meta_db).get_by_email_domain(domain)
        if tenant:
            return tenant.slug
        raise ValueError("tenant_slug is required")
