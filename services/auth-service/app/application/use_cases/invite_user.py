import bcrypt
from sqlalchemy.orm import Session

from app.application.dto.user import InviteUserRequest, UserResponse
from app.infrastructure.config.tenant_connection import get_session_for_tenant
from app.infrastructure.persistence.repositories.user_repository import UserRepository


class InviteUserUseCase:
    def __init__(self, meta_db: Session):
        self._meta_db = meta_db

    def execute(self, request: InviteUserRequest, tenant_slug: str) -> UserResponse:
        password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

        tenant_db = get_session_for_tenant(tenant_slug)
        try:
            repo = UserRepository(tenant_db)
            if repo.get_by_email(request.email) is not None:
                raise ValueError(f"User '{request.email}' already exists in this tenant")

            user = repo.create(
                email=request.email,
                password_hash=password_hash,
                full_name=request.full_name,
            )
            repo.assign_role(user.id, request.role)
            tenant_db.commit()
            roles = repo.get_roles(user.id)

            return UserResponse(
                id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                roles=roles,
            )
        except Exception:
            tenant_db.rollback()
            raise
        finally:
            tenant_db.close()
