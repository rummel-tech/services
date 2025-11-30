"""Test Redis token blacklist functionality with and without Redis."""
import pytest
from unittest.mock import patch, MagicMock
from redis_client import (
    blacklist_token,
    is_token_blacklisted,
    get_redis,
    is_redis_available
)
from auth_service import create_access_token, decode_token
import time


def test_redis_graceful_fallback_when_unavailable():
    """Test that system gracefully handles Redis being unavailable."""
    # When Redis is unavailable, these should not raise exceptions
    result = blacklist_token("test-jti-123", 3600)
    assert result is False  # Returns False when Redis unavailable

    is_blacklisted = is_token_blacklisted("test-jti-123")
    assert is_blacklisted is False  # Fail-open: allows tokens when Redis down


def test_token_creation_includes_jti():
    """Test that created tokens include JTI field."""
    token = create_access_token(data={"sub": "user123", "email": "test@example.com"})
    token_data = decode_token(token)

    assert token_data is not None
    assert token_data.user_id == "user123"
    assert token_data.email == "test@example.com"
    assert token_data.jti is not None  # JTI should be present
    assert token_data.exp is not None  # Expiration should be present
    assert len(token_data.jti) == 36  # UUID format


def test_token_decode_extracts_jti_and_exp():
    """Test that decode_token extracts JTI and exp fields."""
    token = create_access_token(data={"sub": "user456", "email": "user@test.com"})
    token_data = decode_token(token)

    assert token_data.jti is not None
    assert token_data.exp is not None
    assert isinstance(token_data.exp, int)
    assert token_data.exp > int(time.time())  # Expiration in future


@patch('redis_client.get_redis')
def test_blacklist_with_redis_available(mock_get_redis):
    """Test blacklist_token when Redis is available."""
    # Mock Redis client
    mock_redis = MagicMock()
    mock_get_redis.return_value = mock_redis

    # Test blacklisting
    result = blacklist_token("test-jti-456", 7200)

    assert result is True
    mock_redis.setex.assert_called_once_with("blacklist:test-jti-456", 7200, "1")


@patch('redis_client.get_redis')
def test_blacklist_check_with_redis_available(mock_get_redis):
    """Test is_token_blacklisted when Redis is available."""
    # Mock Redis client
    mock_redis = MagicMock()
    mock_redis.exists.return_value = 1  # Token is blacklisted
    mock_get_redis.return_value = mock_redis

    # Test checking blacklist
    is_blacklisted = is_token_blacklisted("test-jti-789")

    assert is_blacklisted is True
    mock_redis.exists.assert_called_once_with("blacklist:test-jti-789")


@patch('redis_client.get_redis')
def test_blacklist_check_token_not_blacklisted(mock_get_redis):
    """Test is_token_blacklisted returns False for non-blacklisted token."""
    # Mock Redis client
    mock_redis = MagicMock()
    mock_redis.exists.return_value = 0  # Token NOT blacklisted
    mock_get_redis.return_value = mock_redis

    # Test checking blacklist
    is_blacklisted = is_token_blacklisted("test-jti-clean")

    assert is_blacklisted is False
    mock_redis.exists.assert_called_once_with("blacklist:test-jti-clean")


def test_get_redis_without_connection():
    """Test that get_redis returns None when Redis unavailable."""
    client = get_redis()
    # In test environment without Redis, should return None
    assert client is None


def test_is_redis_available():
    """Test redis availability check."""
    # In test environment without Redis
    available = is_redis_available()
    assert available is False


if __name__ == "__main__":
    print("Running Redis blacklist tests...")
    print("\n✅ Test 1: Graceful fallback")
    test_redis_graceful_fallback_when_unavailable()
    print("   PASSED - System handles Redis unavailability")

    print("\n✅ Test 2: Token includes JTI")
    test_token_creation_includes_jti()
    print("   PASSED - Tokens contain JTI and exp fields")

    print("\n✅ Test 3: Decode extracts JTI")
    test_token_decode_extracts_jti_and_exp()
    print("   PASSED - decode_token extracts JTI and exp")

    print("\n✅ Test 4: Redis availability check")
    test_get_redis_without_connection()
    test_is_redis_available()
    print("   PASSED - Redis availability correctly reported")

    print("\n✅ Test 5: Blacklist with mocked Redis")
    test_blacklist_with_redis_available()
    test_blacklist_check_with_redis_available()
    test_blacklist_check_token_not_blacklisted()
    print("   PASSED - Blacklist functions work correctly with Redis")

    print("\n" + "="*60)
    print("✅ All tests passed!")
    print("="*60)
    print("\nToken blacklist implementation verified:")
    print("  ✓ Tokens include JTI (JWT ID) for tracking")
    print("  ✓ Graceful fallback when Redis unavailable (fail-open)")
    print("  ✓ Blacklist operations work correctly with Redis")
    print("  ✓ System remains operational without Redis")
