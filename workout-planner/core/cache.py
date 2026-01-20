"""
Cache utilities for Workout Planner.

Delegates to the common library's cache implementation with
workout-planner-specific convenience functions.
"""

import sys
from pathlib import Path
from typing import Optional

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.cache import (
    cache_response,
    invalidate_cache,
    get_cache_stats,
    _generate_cache_key,
)
from common.redis_client import get_redis


def invalidate_user_cache(user_id: str, cache_type: Optional[str] = None) -> bool:
    """
    Invalidate all cached data for a specific user.

    Args:
        user_id: User ID to invalidate cache for
        cache_type: Specific cache type to invalidate (e.g., "readiness", "health_summary")
                   If None, invalidates all cache types for this user

    Returns:
        True if successful, False if Redis unavailable
    """
    if cache_type:
        pattern = f"{cache_type}:{user_id}*"
        return invalidate_cache(pattern)
    else:
        # Invalidate all user-related caches
        patterns = [
            f"readiness:{user_id}*",
            f"health_summary:{user_id}*",
            f"health_trends:{user_id}*",
            f"health_samples:{user_id}*",
        ]

        success = True
        for pattern in patterns:
            if not invalidate_cache(pattern):
                success = False

        return success


__all__ = [
    "cache_response",
    "invalidate_cache",
    "invalidate_user_cache",
    "get_cache_stats",
    "get_redis",
]
