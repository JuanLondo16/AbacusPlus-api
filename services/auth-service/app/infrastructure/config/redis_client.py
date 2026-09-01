import os

import redis

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379"), decode_responses=True
        )
    return _client


def store_refresh_token(jti: str, user_id: str, expire_days: int = 7) -> None:
    get_redis().setex(f"refresh:{jti}", expire_days * 86400, user_id)


def consume_refresh_token(jti: str) -> str | None:
    """Devuelve el user_id y borra la clave de forma atomica. None si no existe.

    Usa `GETDEL` (Redis >= 6.2) en lugar de un `GET` seguido de `DELETE`: entre esas dos
    operaciones caben otras, y dos peticiones simultaneas con el mismo refresh token leian
    ambas el valor antes de que ninguna lo borrara. Las dos obtenian un par de tokens nuevo,
    que es justo lo que la rotacion existe para impedir.

    Si el servidor de Redis es anterior a 6.2 y no conoce el comando, se cae al camino de
    antes para no dejar el login inservible.
    """
    client = get_redis()
    key = f"refresh:{jti}"
    try:
        return client.getdel(key)
    except redis.ResponseError:
        user_id = client.get(key)
        if user_id:
            client.delete(key)
        return user_id


def revoke_refresh_token(jti: str) -> None:
    get_redis().delete(f"refresh:{jti}")
