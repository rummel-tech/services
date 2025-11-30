"""Redis client for token blacklist and caching with graceful fallback."""
import redis
from typing import Optional
from settings import get_settings
from logging_config import get_logger
import threading

log = get_logger("redis")
settings = get_settings()

# Global Redis connection pool
_redis_client: Optional[redis.Redis] = None
_redis_available = False
_redis_lock = threading.Lock()


def init_redis() -> Optional[redis.Redis]:
    """Initialize Redis connection pool with graceful fallback."""
    global _redis_client, _redis_available

    if not settings.redis_enabled:
        log.info("redis_disabled", extra={"reason": "redis_enabled=False"})
        return None

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client

        try:
            # Create connection pool
            pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=10
            )

            # Test connection
            client = redis.Redis(connection_pool=pool)
            client.ping()

            _redis_client = client
            _redis_available = True
            log.info("redis_connected", extra={"url": settings.redis_url})
            return _redis_client

        except (redis.ConnectionError, redis.TimeoutError) as e:
            _redis_available = False
            log.warning("redis_connection_failed", extra={
                "error": str(e),
                "fallback": "Token blacklist disabled"
            })
            return None
        except Exception as e:
            _redis_available = False
            log.error("redis_init_error", extra={"error": str(e)})
            return None


def get_redis() -> Optional[redis.Redis]:
    """Get Redis client, initializing if needed."""
    global _redis_client
    if _redis_client is None:
        return init_redis()
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available."""
    return _redis_available


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    """
    Add token JTI to blacklist with TTL.
    Returns True if successful, False if Redis unavailable.
    """
    client = get_redis()
    if client is None:
        log.warning("blacklist_token_skipped", extra={"reason": "redis_unavailable"})
        return False

    try:
        # Store blacklisted JTI with expiration
        client.setex(f"blacklist:{jti}", ttl_seconds, "1")
        log.info("token_blacklisted", extra={"jti": jti, "ttl": ttl_seconds})
        return True
    except (redis.ConnectionError, redis.TimeoutError) as e:
        log.warning("blacklist_token_failed", extra={"error": str(e), "jti": jti})
        return False


def is_token_blacklisted(jti: str) -> bool:
    """
    Check if token JTI is blacklisted.
    Returns False if Redis unavailable (fail-open for graceful degradation).
    """
    client = get_redis()
    if client is None:
        # Fail-open: allow tokens when Redis is down
        return False

    try:
        exists = client.exists(f"blacklist:{jti}")
        if exists:
            log.info("token_blacklist_check", extra={"jti": jti, "blacklisted": True})
        return exists > 0
    except (redis.ConnectionError, redis.TimeoutError) as e:
        log.warning("blacklist_check_failed", extra={"error": str(e), "jti": jti})
        # Fail-open: allow token when Redis check fails
        return False


# Initialize Redis on module load
init_redis()
