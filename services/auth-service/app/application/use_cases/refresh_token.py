import jwt as pyjwt

from app.application.dto.auth import RefreshRequest, RefreshResponse
from app.infrastructure.config import jwt as jwt_service
from app.infrastructure.config.redis_client import consume_refresh_token, store_refresh_token
from app.infrastructure.config.tenant_connection import get_session_for_tenant
from app.infrastructure.persistence.repositories.user_repository import UserRepository


class RefreshTokenUseCase:
    def execute(self, request: RefreshRequest) -> RefreshResponse:
        try:
            payload = jwt_service.decode_token(request.refresh_token)
        except pyjwt.PyJWTError as exc:
            raise ValueError("Invalid refresh token") from exc

        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")

        jti = payload.get("jti")
        user_id = consume_refresh_token(jti)
        if user_id is None:
            raise ValueError("Refresh token revoked or expired")

        tenant_slug = payload["tenant_slug"]
        tenant_id = payload["tenant_id"]

        tenant_db = get_session_for_tenant(tenant_slug)
        try:
            user_repo = UserRepository(tenant_db)
            user = user_repo.get_by_id(user_id)
            if user is None or not user.is_active:
                raise ValueError("User not found or inactive")
            roles = user_repo.get_roles(user.id)
        finally:
            tenant_db.close()

        new_access = jwt_service.issue_access_token(
            str(user.id), tenant_id, tenant_slug, user.email, roles
        )
        new_refresh, new_jti = jwt_service.issue_refresh_token(str(user.id), tenant_id, tenant_slug)
        store_refresh_token(new_jti, str(user.id))

        return RefreshResponse(access_token=new_access, refresh_token=new_refresh)
