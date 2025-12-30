"""Thin wrapper to keep legacy tests working by delegating to core.redis_client."""
from core.redis_client import (
    get_redis,
    is_redis_available,
    is_token_blacklisted,
    blacklist_token,
)

__all__ = [
    "get_redis",
    "is_redis_available",
    "is_token_blacklisted",
    "blacklist_token",
]
