from passlib.context import CryptContext
from app.domain.ports.services import PasswordHasherPort


class BcryptPasswordHasher(PasswordHasherPort):
    def __init__(self):
        self._context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash(self, password: str) -> str:
        return self._context.hash(password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return self._context.verify(plain_password, hashed_password)
