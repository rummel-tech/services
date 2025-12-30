"""Compatibility shim that honors test mocks while delegating to core.redis_client."""
from core import redis_client as core_redis


def get_redis():
    # Allow tests to patch this function directly
    return core_redis.get_redis()


def is_redis_available() -> bool:
    return core_redis.is_redis_available()


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    # Use local get_redis so test patches take effect
    client = get_redis()
    if client is None:
        return False
    try:
        client.setex(f"blacklist:{jti}", ttl_seconds, "1")
        return True
    except Exception:
        return False


def is_token_blacklisted(jti: str) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return client.exists(f"blacklist:{jti}") > 0
    except Exception:
        return False


__all__ = [
    "get_redis",
    "is_redis_available",
    "is_token_blacklisted",
    "blacklist_token",
]
