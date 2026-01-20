"""
Cache shim for Workout Planner.

Provides a test-patchable interface that delegates to the common library.
"""

import sys
from pathlib import Path

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-export from redis_client for backward compatibility
from redis_client import get_redis

# Re-export from common.cache
from common.cache import (
    cache_response,
    invalidate_cache,
    get_cache_stats,
)

__all__ = [
    "get_redis",
    "cache_response",
    "invalidate_cache",
    "get_cache_stats",
]
