"""
Response caching with Redis backend and graceful fallback.
"""

import json
import hashlib
import logging
from typing import Optional, Any, Callable
from functools import wraps

from . import redis_client
from . import metrics

logger = logging.getLogger(__name__)


def _generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate deterministic cache key from function arguments."""
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))

    key_string = ":".join(key_parts)

    # Hash for very long keys
    if len(key_string) > 200:
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"{prefix}:{key_hash}"

    return key_string


def cache_response(prefix: str, ttl_seconds: int = 300):
    """
    Decorator to cache function response in Redis.

    Args:
        prefix: Cache key prefix (e.g., "readiness", "health_summary")
        ttl_seconds: Time to live in seconds (default 5 minutes)

    Usage:
        @cache_response("user_data", ttl_seconds=300)
        def get_user_data(user_id: str):
            # expensive operation
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            client = redis_client.get_redis()

            # If Redis unavailable, skip caching
            if client is None:
                logger.debug(f"Cache skip (Redis unavailable): {func.__name__}")
                return func(*args, **kwargs)

            # Generate cache key
            cache_key = _generate_cache_key(prefix, *args, **kwargs)

            try:
                # Try to get cached value
                cached_value = client.get(cache_key)

                if cached_value:
                    # Cache hit
                    logger.debug(f"Cache hit: {cache_key}")
                    metrics.record_cache_operation("hit")
                    return json.loads(cached_value)

                # Cache miss - execute function
                logger.debug(f"Cache miss: {cache_key}")
                metrics.record_cache_operation("miss")
                result = func(*args, **kwargs)

                # Store in cache
                try:
                    client.setex(
                        cache_key,
                        ttl_seconds,
                        json.dumps(result, default=str)
                    )
                except (TypeError, ValueError) as e:
                    logger.warning(f"Cache serialize failed: {e}")

                return result

            except Exception as e:
                logger.warning(f"Cache operation failed: {e}")
                metrics.record_cache_operation("error")
                return func(*args, **kwargs)

        return wrapper
    return decorator


def invalidate_cache(pattern: str) -> bool:
    """
    Invalidate all cache entries matching a pattern.

    Args:
        pattern: Redis key pattern (e.g., "user:123:*")

    Returns:
        True if successful, False if Redis unavailable
    """
    client = redis_client.get_redis()

    if client is None:
        logger.debug("Cache invalidate skipped: Redis unavailable")
        return False

    try:
        keys = client.keys(pattern)

        if keys:
            deleted_count = client.delete(*keys)
            logger.info(f"Cache invalidated: {pattern} ({deleted_count} keys)")
            metrics.record_cache_operation("invalidated")
            return True
        else:
            logger.debug(f"Cache invalidate: no keys match {pattern}")
            return True

    except Exception as e:
        logger.warning(f"Cache invalidate failed: {e}")
        return False


def get_cache_stats() -> dict:
    """
    Get cache statistics from Redis.

    Returns:
        Dictionary with cache stats or unavailable status
    """
    client = redis_client.get_redis()

    if client is None:
        return {"available": False}

    try:
        info = client.info("stats")

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        return {
            "available": True,
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": hits,
            "keyspace_misses": misses,
            "hit_rate": round(hits / max(total, 1), 3)
        }
    except Exception as e:
        logger.warning(f"Cache stats failed: {e}")
        return {"available": False, "error": str(e)}
