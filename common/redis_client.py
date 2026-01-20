"""
Redis client with graceful fallback for caching and token blacklist.
"""

import threading
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global Redis state
_redis_client = None
_redis_available = False
_redis_lock = threading.Lock()
_redis_settings = {
    "enabled": False,
    "url": "redis://localhost:6379/0"
}


def configure_redis(enabled: bool = False, url: str = "redis://localhost:6379/0") -> None:
    """
    Configure Redis settings.

    Args:
        enabled: Whether Redis is enabled
        url: Redis connection URL
    """
    global _redis_settings
    _redis_settings = {
        "enabled": enabled,
        "url": url
    }


def init_redis():
    """
    Initialize Redis connection pool with graceful fallback.

    Returns:
        Redis client or None if unavailable
    """
    global _redis_client, _redis_available

    if not _redis_settings["enabled"]:
        logger.info("Redis disabled via configuration")
        return None

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client

        try:
            import redis as redis_lib

            # Create connection pool
            pool = redis_lib.ConnectionPool.from_url(
                _redis_settings["url"],
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=10
            )

            # Test connection
            client = redis_lib.Redis(connection_pool=pool)
            client.ping()

            _redis_client = client
            _redis_available = True
            logger.info(f"Redis connected: {_redis_settings['url']}")
            return _redis_client

        except ImportError:
            _redis_available = False
            logger.warning("redis package not installed")
            return None
        except Exception as e:
            _redis_available = False
            logger.warning(f"Redis connection failed: {e}")
            return None


def get_redis():
    """
    Get Redis client, initializing if needed.

    Returns:
        Redis client or None if unavailable
    """
    global _redis_client
    if _redis_client is None:
        return init_redis()
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available."""
    return _redis_available


def close_redis() -> None:
    """Close Redis connection pool."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
        _redis_available = False


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    """
    Add token JTI to blacklist with TTL.

    Args:
        jti: JWT ID to blacklist
        ttl_seconds: Time to live in seconds

    Returns:
        True if successful, False if Redis unavailable
    """
    client = get_redis()
    if client is None:
        logger.warning("Token blacklist skipped: Redis unavailable")
        return False

    try:
        client.setex(f"blacklist:{jti}", ttl_seconds, "1")
        logger.info(f"Token blacklisted: {jti[:8]}...")
        return True
    except Exception as e:
        logger.warning(f"Token blacklist failed: {e}")
        return False


def is_token_blacklisted(jti: str) -> bool:
    """
    Check if token JTI is blacklisted.

    Args:
        jti: JWT ID to check

    Returns:
        True if blacklisted, False if not or Redis unavailable (fail-open)
    """
    client = get_redis()
    if client is None:
        # Fail-open: allow tokens when Redis is down
        return False

    try:
        exists = client.exists(f"blacklist:{jti}")
        return exists > 0
    except Exception as e:
        logger.warning(f"Blacklist check failed: {e}")
        # Fail-open
        return False
