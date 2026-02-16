import logging
from datetime import timedelta

from app.infrastructure.persistence.models.user import User
from app.application.dto.user import CreateUserRequest, UserResponse
from app.domain.ports.repositories import UserRepositoryPort
from app.domain.ports.services import PasswordHasherPort, TokenServicePort
from app.domain.exceptions.base import (
    DuplicateEntityException,
    AuthenticationException,
    DomainException,
)

logger = logging.getLogger(__name__)


class CreateUserUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryPort,
        password_hasher: PasswordHasherPort,
    ):
        self.user_repo = user_repo
        self.password_hasher = password_hasher

    def execute(self, user_data: CreateUserRequest) -> UserResponse:
        if self.user_repo.get_by_username(user_data.username):
            raise DuplicateEntityException("User", user_data.username)

        if self.user_repo.get_by_email(user_data.email):
            raise DuplicateEntityException("User", user_data.email)

        db_user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=self.password_hasher.hash(user_data.password),
            full_name=user_data.full_name,
            tenant_id=user_data.tenant_id,
        )
        created = self.user_repo.create(db_user)
        logger.info("User created: %s", created.username)
        return UserResponse.model_validate(created, from_attributes=True)


class AuthenticateUserUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryPort,
        password_hasher: PasswordHasherPort,
        token_service: TokenServicePort,
        expire_minutes: int = 30,
    ):
        self.user_repo = user_repo
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.expire_minutes = expire_minutes

    def execute(self, username: str, password: str) -> dict:
        user = self.user_repo.get_by_username(username)
        if not user:
            raise AuthenticationException("Incorrect username or password")
        if not self.password_hasher.verify(password, user.hashed_password):
            raise AuthenticationException("Incorrect username or password")

        access_token_expires = timedelta(minutes=self.expire_minutes)
        access_token = self.token_service.create_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )

        self.user_repo.update_last_login(user)
        logger.info("Login successful: %s", username)

        return {
            "access_token": access_token,
            "user": user,
        }
