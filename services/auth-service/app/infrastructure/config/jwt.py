import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

_private_key = None
_public_key = None


def _load_private_key():
    global _private_key
    if _private_key is None:
        raw = os.environ["JWT_PRIVATE_KEY"].replace("\\n", "\n").encode()
        _private_key = load_pem_private_key(raw, password=None)
    return _private_key


def _load_public_key():
    global _public_key
    if _public_key is None:
        raw = os.environ["JWT_PUBLIC_KEY"].replace("\\n", "\n").encode()
        _public_key = load_pem_public_key(raw)
    return _public_key


def issue_access_token(
    user_id: str, tenant_id: str, tenant_slug: str, email: str, roles: list[str]
) -> str:
    expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "tenant_slug": tenant_slug,
        "email": email,
        "roles": roles,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, _load_private_key(), algorithm="RS256")


def issue_refresh_token(user_id: str, tenant_id: str, tenant_slug: str) -> tuple[str, str]:
    expire_days = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "tenant_slug": tenant_slug,
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=expire_days),
    }
    token = jwt.encode(payload, _load_private_key(), algorithm="RS256")
    return token, jti


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        _load_public_key(),
        algorithms=["RS256"],
        options={"require": ["sub", "tenant_id", "tenant_slug", "exp", "type"]},
    )
