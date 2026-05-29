import os

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key

_public_key = None


def _load_public_key():
    global _public_key
    if _public_key is None:
        raw = os.environ["JWT_PUBLIC_KEY"].replace("\\n", "\n").encode()
        _public_key = load_pem_public_key(raw)
    return _public_key


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on failure."""
    return jwt.decode(
        token,
        _load_public_key(),
        algorithms=["RS256"],
        options={"require": ["sub", "tenant_id", "tenant_slug", "exp", "type"]},
    )
