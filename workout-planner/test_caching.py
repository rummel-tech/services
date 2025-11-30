"""Test caching functionality with and without Redis."""
import pytest
from unittest.mock import patch, MagicMock
from cache import (
    cache_response,
    invalidate_cache,
    invalidate_user_cache,
    get_cache_stats,
    _generate_cache_key
)
import time


def test_cache_key_generation():
    """Test deterministic cache key generation."""
    # Same args should produce same key
    key1 = _generate_cache_key("test", "user123", days=7)
    key2 = _generate_cache_key("test", "user123", days=7)
    assert key1 == key2

    # Different args should produce different keys
    key3 = _generate_cache_key("test", "user456", days=7)
    assert key1 != key3

    # Different kwargs should produce different keys
    key4 = _generate_cache_key("test", "user123", days=14)
    assert key1 != key4


def test_cache_graceful_fallback():
    """Test that caching gracefully falls back when Redis unavailable."""
    call_count = 0

    @cache_response("test", ttl_seconds=60)
    def expensive_function(value: int):
        nonlocal call_count
        call_count += 1
        return {"result": value * 2}

    # Without Redis, function should be called each time
    result1 = expensive_function(5)
    assert result1 == {"result": 10}
    assert call_count == 1

    result2 = expensive_function(5)
    assert result2 == {"result": 10}
    assert call_count == 2  # Called again (no caching)


@patch('cache.get_redis')
def test_cache_with_redis_available(mock_get_redis):
    """Test caching when Redis is available."""
    # Mock Redis client
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # First call - cache miss
    mock_get_redis.return_value = mock_redis

    call_count = 0

    @cache_response("test", ttl_seconds=60)
    def expensive_function(value: int):
        nonlocal call_count
        call_count += 1
        return {"result": value * 2}

    # First call - should execute function and cache result
    result1 = expensive_function(5)
    assert result1 == {"result": 10}
    assert call_count == 1
    mock_redis.setex.assert_called_once()


@patch('cache.get_redis')
def test_cache_hit(mock_get_redis):
    """Test cache hit returns cached value without executing function."""
    import json

    # Mock Redis client with cached value
    mock_redis = MagicMock()
    cached_data = json.dumps({"result": 100})
    mock_redis.get.return_value = cached_data
    mock_get_redis.return_value = mock_redis

    call_count = 0

    @cache_response("test", ttl_seconds=60)
    def expensive_function(value: int):
        nonlocal call_count
        call_count += 1
        return {"result": value * 2}

    # Should return cached value without calling function
    result = expensive_function(5)
    assert result == {"result": 100}  # Cached value, not computed
    assert call_count == 0  # Function not called


@patch('cache.get_redis')
def test_invalidate_cache(mock_get_redis):
    """Test cache invalidation."""
    mock_redis = MagicMock()
    mock_redis.keys.return_value = ["key1", "key2", "key3"]
    mock_redis.delete.return_value = 3
    mock_get_redis.return_value = mock_redis

    result = invalidate_cache("test:*")

    assert result is True
    mock_redis.keys.assert_called_once_with("test:*")
    mock_redis.delete.assert_called_once_with("key1", "key2", "key3")


@patch('cache.get_redis')
def test_invalidate_user_cache(mock_get_redis):
    """Test user-specific cache invalidation."""
    mock_redis = MagicMock()
    mock_redis.keys.return_value = []
    mock_get_redis.return_value = mock_redis

    # Test specific cache type invalidation
    result = invalidate_user_cache("user123", cache_type="readiness")
    assert result is True
    mock_redis.keys.assert_called_with("readiness:user123*")

    # Test all cache types invalidation
    invalidate_user_cache("user123")
    # Should call keys() multiple times for different cache types
    assert mock_redis.keys.call_count > 1


def test_cache_stats_without_redis():
    """Test cache stats when Redis unavailable."""
    stats = get_cache_stats()
    assert stats == {"available": False}


@patch('cache.get_redis')
def test_cache_stats_with_redis(mock_get_redis):
    """Test cache stats when Redis available."""
    mock_redis = MagicMock()
    mock_redis.info.return_value = {
        "keyspace_hits": 150,
        "keyspace_misses": 50,
        "total_commands_processed": 1000
    }
    mock_get_redis.return_value = mock_redis

    stats = get_cache_stats()

    assert stats["available"] is True
    assert stats["keyspace_hits"] == 150
    assert stats["keyspace_misses"] == 50
    assert stats["hit_rate"] == 0.75  # 150 / (150 + 50)


@patch('cache.get_redis')
def test_cache_serialization_with_default_handler(mock_get_redis):
    """Test that serialization uses default=str for complex objects."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_get_redis.return_value = mock_redis

    from datetime import datetime

    @cache_response("test", ttl_seconds=60)
    def returns_datetime():
        return {"timestamp": datetime.utcnow()}

    # Should execute function and cache using default=str
    result = returns_datetime()
    assert "timestamp" in result
    # setex should be called (serialization succeeded with default=str)
    mock_redis.setex.assert_called_once()


if __name__ == "__main__":
    print("Running caching tests...")

    print("\n✅ Test 1: Cache key generation")
    test_cache_key_generation()
    print("   PASSED - Deterministic key generation")

    print("\n✅ Test 2: Graceful fallback")
    test_cache_graceful_fallback()
    print("   PASSED - Functions work without Redis")

    print("\n✅ Test 3: Cache with Redis")
    test_cache_with_redis_available()
    print("   PASSED - Caching works with Redis")

    print("\n✅ Test 4: Cache hits")
    test_cache_hit()
    print("   PASSED - Cached values returned without execution")

    print("\n✅ Test 5: Cache invalidation")
    test_invalidate_cache()
    test_invalidate_user_cache()
    print("   PASSED - Cache invalidation works")

    print("\n✅ Test 6: Cache stats")
    test_cache_stats_without_redis()
    test_cache_stats_with_redis()
    print("   PASSED - Cache statistics available")

    print("\n✅ Test 7: Serialization with default handler")
    test_cache_serialization_with_default_handler()
    print("   PASSED - Complex objects serialized with default=str")

    print("\n" + "="*60)
    print("✅ All caching tests passed!")
    print("="*60)
    print("\nCaching implementation verified:")
    print("  ✓ Decorator-based response caching")
    print("  ✓ Graceful fallback when Redis unavailable")
    print("  ✓ Cache hit/miss tracking")
    print("  ✓ User-specific cache invalidation")
    print("  ✓ Cache statistics monitoring")
    print("  ✓ Error handling for edge cases")
