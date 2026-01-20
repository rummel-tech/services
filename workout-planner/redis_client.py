"""
Redis client shim for Workout Planner.

Provides a test-patchable interface that delegates to the common library.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import redis_client as common_redis


def get_redis():
    """Get Redis client. Can be patched in tests."""
    return common_redis.get_redis()


def is_redis_available() -> bool:
    """Check if Redis is available."""
    return common_redis.is_redis_available()


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    """Add token to blacklist."""
    return common_redis.blacklist_token(jti, ttl_seconds)


def is_token_blacklisted(jti: str) -> bool:
    """Check if token is blacklisted."""
    return common_redis.is_token_blacklisted(jti)


__all__ = [
    "get_redis",
    "is_redis_available",
    "blacklist_token",
    "is_token_blacklisted",
]
