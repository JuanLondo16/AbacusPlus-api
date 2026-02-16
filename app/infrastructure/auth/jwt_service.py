import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv

from app.domain.ports.services import TokenServicePort
from app.domain.exceptions.base import DomainException

load_dotenv()

logger = logging.getLogger(__name__)


class JWTService(TokenServicePort):
    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY")
        self.algorithm = os.getenv("ALGORITHM", "HS256")
        self.expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    def create_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=self.expire_minutes))
        to_encode["exp"] = expire
        try:
            return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        except Exception as e:
            logger.error("Error creating token: %s", str(e))
            raise DomainException("Failed to create access token")

    def decode_token(self, token: str) -> dict:
        return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
