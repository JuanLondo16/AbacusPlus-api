import os
import redis

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379"), decode_responses=True)
    return _client


def store_refresh_token(jti: str, user_id: str, expire_days: int = 7) -> None:
    get_redis().setex(f"refresh:{jti}", expire_days * 86400, user_id)


def consume_refresh_token(jti: str) -> str | None:
    """Returns user_id and deletes the key atomically. Returns None if not found."""
    client = get_redis()
    key = f"refresh:{jti}"
    user_id = client.get(key)
    if user_id:
        client.delete(key)
    return user_id


def revoke_refresh_token(jti: str) -> None:
    get_redis().delete(f"refresh:{jti}")
