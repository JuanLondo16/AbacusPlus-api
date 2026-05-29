from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.infrastructure.config.jwt_validator import decode_token
from app.infrastructure.config.tenant_connection_manager import get_session_for_tenant

_bearer = HTTPBearer()


class TokenData:
    def __init__(self, payload: dict, raw_token: str):
        self.user_id = payload["sub"]
        self.tenant_id = payload["tenant_id"]
        self.tenant_slug = payload["tenant_slug"]
        self.roles: list[str] = payload.get("roles", [])
        self.email: str = payload.get("email", "")
        self.raw_token = raw_token


def get_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> TokenData:
    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    return TokenData(payload, credentials.credentials)


def get_tenant_db(token: Annotated[TokenData, Depends(get_token_data)]):
    db = get_session_for_tenant(token.tenant_slug)
    try:
        yield db
    finally:
        db.close()
