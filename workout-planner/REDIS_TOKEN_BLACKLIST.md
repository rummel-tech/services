# Redis Token Blacklist Implementation

## Overview

Implemented JWT token blacklist using Redis to enable secure logout functionality. The system supports graceful degradation when Redis is unavailable, ensuring the application remains operational.

## Architecture

### Components

1. **redis_client.py** - Redis connection management and blacklist operations
2. **auth_service.py** - Token creation with JTI (JWT ID) tracking
3. **routers/auth.py** - Authentication endpoints with blacklist checks
4. **main.py** - Redis health monitoring in `/ready` endpoint

### Token Structure

Every JWT token now includes:
- `jti`: Unique JWT ID (UUID) for tracking individual tokens
- `exp`: Expiration timestamp for TTL calculation
- `sub`: User ID
- `email`: User email
- `type`: Token type (access or refresh)

## Features

### 1. Token Blacklisting on Logout

When a user logs out:
```python
POST /auth/logout
Authorization: Bearer <token>
```

The system:
1. Extracts the JTI from the token
2. Calculates TTL based on token expiration
3. Stores `blacklist:<jti>` in Redis with TTL
4. Returns success message

**Example:**
```json
{
  "message": "Successfully logged out"
}
```

### 2. Blacklist Verification

On every authenticated request, `get_current_user` dependency:
1. Decodes the JWT token
2. Extracts the JTI
3. Checks if `blacklist:<jti>` exists in Redis
4. Returns 401 if blacklisted

**Blacklisted Token Response:**
```json
{
  "detail": "Token has been revoked"
}
```

### 3. Graceful Fallback

When Redis is unavailable:
- **blacklist_token()**: Returns False, logs warning
- **is_token_blacklisted()**: Returns False (fail-open)
- Application continues operating normally
- Security degrades to expiration-based validation only

**Rationale:** Better to allow legitimate requests than cause service outage. Tokens still expire naturally.

## Configuration

### settings.py

```python
redis_url: str = "redis://localhost:6379/0"
redis_enabled: bool = True
```

### Environment Variables

```bash
# Redis connection
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true

# For production with Redis authentication
REDIS_URL=redis://:password@redis.example.com:6379/0

# Disable Redis (fallback mode)
REDIS_ENABLED=false
```

## Redis Data Structure

### Blacklist Keys

```
Key: blacklist:<jti>
Value: "1"
TTL: <seconds until token expiration>
Type: String
```

**Example:**
```
blacklist:a1b2c3d4-e5f6-7890-abcd-ef1234567890
Value: "1"
TTL: 86400 seconds (24 hours)
```

### TTL Strategy

- Minimum TTL: 60 seconds
- Default TTL: `token.exp - current_time`
- Automatic expiration when token would naturally expire
- No manual cleanup needed

## Health Monitoring

### /ready Endpoint

```json
{
  "status": "ready" | "degraded",
  "environment": "development",
  "db": "ok" | "error",
  "redis": "ok" | "error" | "disabled"
}
```

**Status Logic:**
- `ready`: DB ok, Redis ok (or disabled)
- `degraded`: DB ok, Redis expected but failed
- `degraded`: DB failed (regardless of Redis)

## Testing

### Unit Tests

`test_redis_blacklist.py` verifies:
- ✅ Tokens include JTI and exp fields
- ✅ decode_token extracts JTI correctly
- ✅ Graceful fallback when Redis unavailable
- ✅ Blacklist operations with mocked Redis
- ✅ System remains operational without Redis

**Run tests:**
```bash
python test_redis_blacklist.py
```

### Integration Testing

**With Redis Available:**
```bash
# 1. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 2. Test flow
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "TestPass123!"}'

# Extract access_token from response

curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>"  # Success

curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer <token>"  # Blacklist token

curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>"  # 401 - Token has been revoked
```

**Without Redis (Graceful Fallback):**
```bash
# Same flow, but tokens remain valid after logout
# System logs warnings but continues operating
```

## Production Deployment

### Prerequisites

1. **Redis Server**
   ```bash
   # Option 1: Docker
   docker run -d --name redis \
     -p 6379:6379 \
     -v redis_data:/data \
     redis:7-alpine redis-server --appendonly yes

   # Option 2: AWS ElastiCache
   # Option 3: Redis Cloud
   ```

2. **Redis Configuration**
   ```bash
   # Set in environment
   export REDIS_URL="redis://:password@redis.prod.example.com:6379/0"
   export REDIS_ENABLED=true
   ```

3. **Connection Pooling**
   - Max connections: 10
   - Socket timeout: 5 seconds
   - Retry on timeout: enabled

### Monitoring

**Key Metrics:**
- `redis_connection_failed`: Redis connection errors
- `token_blacklisted`: Successful blacklist operations
- `blacklist_token_skipped`: Blacklist attempts when Redis down
- `auth_token_blacklisted`: Blocked blacklisted token usage

**Log Queries:**
```bash
# Check Redis connection issues
grep "redis_connection_failed" /var/log/app.log

# Monitor blacklist operations
grep "token_blacklisted" /var/log/app.log

# Check for revoked token usage attempts
grep "auth_token_blacklisted" /var/log/app.log
```

### High Availability

**Redis Cluster Setup:**
```python
# For production with Redis Sentinel/Cluster
from redis.sentinel import Sentinel

sentinel = Sentinel([
    ('sentinel1', 26379),
    ('sentinel2', 26379),
    ('sentinel3', 26379)
], socket_timeout=5)

master = sentinel.master_for('mymaster', socket_timeout=5)
```

## Security Considerations

### Strengths

1. **Immediate Token Revocation**: Tokens invalidated on logout
2. **Automatic Cleanup**: TTL ensures old blacklist entries expire
3. **Graceful Degradation**: System remains operational if Redis fails
4. **JTI Uniqueness**: Each token has unique ID for precise tracking

### Limitations

1. **Redis Dependency**: Blacklist only works when Redis available
2. **Fail-Open Design**: When Redis down, tokens work until expiration
3. **Network Latency**: Redis check adds ~1-2ms per authenticated request
4. **Memory Usage**: Each blacklisted token ~50 bytes in Redis

### Mitigation Strategies

1. **Short Token Lifetimes**: 24 hours for access tokens
2. **Refresh Token Rotation**: New tokens on refresh
3. **Redis Monitoring**: Alert on connection failures
4. **Multiple Redis Instances**: Master-replica setup

## Performance Impact

### Baseline (Without Redis Check)

- P50: 6ms
- P95: 7ms
- P99: 15ms

### With Redis Check (Local Redis)

- Additional latency: ~1-2ms per request
- Expected P95: ~9ms (still excellent)
- Expected P99: ~17ms

### Optimization

- Connection pooling reduces overhead
- TTL-based expiration eliminates cleanup jobs
- Local Redis deployment minimizes network latency

## Troubleshooting

### Redis Connection Failed

**Symptom:**
```
redis_connection_failed - Token blacklist disabled
```

**Causes:**
1. Redis not running
2. Incorrect REDIS_URL
3. Network/firewall issues
4. Redis authentication failed

**Resolution:**
```bash
# Check Redis status
redis-cli ping  # Should return PONG

# Test connection
redis-cli -u redis://localhost:6379/0 ping

# Check logs
tail -f /var/log/redis/redis-server.log
```

### Token Still Valid After Logout

**Symptom:** Token works after calling /logout

**Causes:**
1. Redis unavailable (graceful fallback active)
2. Wrong JTI extracted
3. Redis key not set

**Debug:**
```bash
# Check Redis has the blacklist key
redis-cli KEYS "blacklist:*"

# Check specific token
redis-cli GET "blacklist:<jti>"
redis-cli TTL "blacklist:<jti>"
```

### High Memory Usage in Redis

**Symptom:** Redis memory growing

**Causes:**
1. TTL not set correctly
2. Many active sessions

**Resolution:**
```bash
# Check memory usage
redis-cli INFO memory

# Check key count
redis-cli DBSIZE

# Check TTL on keys
redis-cli TTL "blacklist:<jti>"

# Set maxmemory policy
redis-cli CONFIG SET maxmemory-policy volatile-ttl
```

## Future Enhancements

### Planned Features

1. **Revoke All User Tokens**: Blacklist all tokens for a user
   ```python
   POST /auth/revoke-all-sessions
   ```

2. **Token Refresh Blacklist**: Track and invalidate refresh tokens
   ```python
   blacklist_token(refresh_token.jti, refresh_token.exp)
   ```

3. **Admin Token Revocation**: Admin endpoint to revoke any token
   ```python
   POST /admin/tokens/<jti>/revoke
   ```

4. **Redis Sentinel Support**: High availability Redis setup
5. **Token Usage Analytics**: Track token usage patterns

### Monitoring Dashboard

Future CloudWatch/Grafana metrics:
- Blacklist hit rate
- Redis operation latency
- Failed blacklist attempts
- Active blacklisted tokens count

## References

- JWT Best Practices: https://datatracker.ietf.org/doc/html/rfc8725
- Redis Data Types: https://redis.io/docs/data-types/
- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/

## Implementation Date

2025-11-21

## Version

1.0.0
