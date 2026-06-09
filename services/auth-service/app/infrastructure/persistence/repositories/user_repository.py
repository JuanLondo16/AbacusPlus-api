from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.user import User, UserRole


class UserRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_email(self, email: str) -> Optional[User]:
        return self._db.query(User).filter(User.email == email, User.is_active == True).first()

    def get_by_id(self, user_id) -> Optional[User]:
        return self._db.query(User).filter(User.id == user_id).first()

    def get_roles(self, user_id) -> list[str]:
        roles = self._db.query(UserRole).filter(UserRole.user_id == user_id).all()
        return [r.role for r in roles]

    def list_users(self) -> list[User]:
        return self._db.query(User).filter(User.is_active == True).order_by(User.created_at).all()

    def create(self, email: str, password_hash: str, full_name: Optional[str] = None) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        self._db.add(user)
        self._db.flush()
        return user

    def assign_role(self, user_id, role: str) -> None:
        existing = (
            self._db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role == role)
            .first()
        )
        if not existing:
            self._db.add(UserRole(user_id=user_id, role=role))
        self._db.commit()
