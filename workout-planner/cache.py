"""Response caching with Redis backend and graceful fallback."""
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
from redis_client import get_redis
from logging_config import get_logger
import metrics

log = get_logger("cache")


def _generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate deterministic cache key from function arguments."""
    # Create a string representation of args and kwargs
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))

    # Hash for consistent length keys
    key_string = ":".join(key_parts)
    if len(key_string) > 200:
        # Use hash for very long keys
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
        @cache_response("readiness", ttl_seconds=300)
        def get_readiness(user_id: str):
            # expensive operation
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            redis_client = get_redis()

            # If Redis unavailable, skip caching
            if redis_client is None:
                log.debug("cache_skip_redis_unavailable", extra={"function": func.__name__})
                return func(*args, **kwargs)

            # Generate cache key
            cache_key = _generate_cache_key(prefix, *args, **kwargs)

            try:
                # Try to get cached value
                cached_value = redis_client.get(cache_key)

                if cached_value:
                    # Cache hit
                    log.debug("cache_hit", extra={"key": cache_key, "function": func.__name__})
                    metrics.record_domain_event("cache_hit")
                    metrics.record_cache_operation("hit")
                    return json.loads(cached_value)

                # Cache miss - execute function
                log.debug("cache_miss", extra={"key": cache_key, "function": func.__name__})
                metrics.record_domain_event("cache_miss")
                metrics.record_cache_operation("miss")
                result = func(*args, **kwargs)

                # Store in cache
                try:
                    redis_client.setex(
                        cache_key,
                        ttl_seconds,
                        json.dumps(result, default=str)  # default=str handles datetime
                    )
                    log.debug("cache_set", extra={"key": cache_key, "ttl": ttl_seconds})
                except (TypeError, ValueError) as e:
                    # JSON serialization failed - skip caching this result
                    log.warning("cache_serialize_failed", extra={
                        "key": cache_key,
                        "error": str(e),
                        "function": func.__name__
                    })

                return result

            except Exception as e:
                # Redis operation failed - fall back to executing function
                log.warning("cache_operation_failed", extra={
                    "key": cache_key,
                    "error": str(e),
                    "function": func.__name__
                })
                metrics.record_domain_event("cache_error")
                metrics.record_cache_operation("error")
                return func(*args, **kwargs)

        return wrapper
    return decorator


def invalidate_cache(pattern: str) -> bool:
    """
    Invalidate all cache entries matching a pattern.

    Args:
        pattern: Redis key pattern (e.g., "readiness:user123:*")

    Returns:
        True if successful, False if Redis unavailable
    """
    redis_client = get_redis()

    if redis_client is None:
        log.debug("cache_invalidate_skip", extra={"reason": "redis_unavailable"})
        return False

    try:
        # Find all keys matching pattern
        keys = redis_client.keys(pattern)

        if keys:
            deleted_count = redis_client.delete(*keys)
            log.info("cache_invalidated", extra={
                "pattern": pattern,
                "keys_deleted": deleted_count
            })
            metrics.record_domain_event("cache_invalidated")
            metrics.record_cache_operation("invalidated")
            return True
        else:
            log.debug("cache_invalidate_no_keys", extra={"pattern": pattern})
            return True

    except Exception as e:
        log.warning("cache_invalidate_failed", extra={
            "pattern": pattern,
            "error": str(e)
        })
        return False


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

    return invalidate_cache(pattern)


def get_cache_stats() -> dict:
    """
    Get cache statistics from Redis.

    Returns:
        Dictionary with cache stats or empty dict if Redis unavailable
    """
    redis_client = get_redis()

    if redis_client is None:
        return {"available": False}

    try:
        info = redis_client.info("stats")

        return {
            "available": True,
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": round(
                info.get("keyspace_hits", 0) /
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1),
                3
            )
        }
    except Exception as e:
        log.warning("cache_stats_failed", extra={"error": str(e)})
        return {"available": False, "error": str(e)}
