from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.user import User
from app.domain.ports.repositories import UserRepositoryPort


class UserRepository(UserRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_last_login(self, user: User) -> None:
        user.last_login = datetime.now(timezone.utc)
        self.db.commit()
