"""Redis client for token blacklisting — delegates to common."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from common.redis_client import (
    configure_redis,
    init_redis,
    get_redis,
    is_redis_available,
    close_redis,
    blacklist_token,
    is_token_blacklisted,
)

__all__ = [
    "configure_redis",
    "init_redis",
    "get_redis",
    "is_redis_available",
    "close_redis",
    "blacklist_token",
    "is_token_blacklisted",
]
