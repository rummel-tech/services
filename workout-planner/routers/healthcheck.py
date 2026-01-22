"""
Health check endpoints for monitoring and deployment validation.

Provides comprehensive health checks including database connectivity,
cache availability, and service status.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from core.database import get_db, get_cursor, USE_SQLITE
from core.logging_config import get_logger
from core.settings import get_settings
import time

log = get_logger("api.healthcheck")
settings = get_settings()

router = APIRouter(tags=["healthcheck"])


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    database: str
    database_healthy: bool
    database_latency_ms: Optional[float] = None
    environment: str


class DetailedHealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: str
    database: dict
    cache: dict
    uptime: Optional[float] = None


@router.get("/healthz", response_model=HealthCheckResponse)
def basic_health_check():
    """
    Basic health check endpoint.

    Returns 200 OK if service is running. Does not check dependencies.
    Suitable for Kubernetes liveness probes.
    """
    return HealthCheckResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        database="sqlite" if USE_SQLITE else "postgresql",
        database_healthy=True,
        environment=settings.environment,
    )


@router.get("/readyz", response_model=DetailedHealthResponse)
def readiness_check():
    """
    Readiness check endpoint with dependency validation.

    Returns 200 OK only if all dependencies (database, cache) are healthy.
    Suitable for Kubernetes readiness probes and deployment validation.
    Returns 503 Service Unavailable if any dependency is unhealthy.
    """
    timestamp = datetime.utcnow().isoformat()
    database_info = check_database()
    cache_info = check_cache()

    # Determine overall status
    all_healthy = database_info["healthy"] and cache_info["healthy"]
    overall_status = "ok" if all_healthy else "degraded"

    response = DetailedHealthResponse(
        status=overall_status,
        timestamp=timestamp,
        version="1.0.0",
        environment=settings.environment,
        database=database_info,
        cache=cache_info,
    )

    # Return 503 if not ready
    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(),
        )

    return response


def check_database() -> dict:
    """
    Check database connectivity and measure latency.

    Returns:
        dict with keys: healthy (bool), type (str), latency_ms (float), error (str|None)
    """
    db_type = "sqlite" if USE_SQLITE else "postgresql"

    try:
        start_time = time.time()

        with get_db() as conn:
            cur = get_cursor(conn)
            # Simple query to test connectivity
            if USE_SQLITE:
                cur.execute("SELECT 1")
            else:
                cur.execute("SELECT 1 AS health_check")
            result = cur.fetchone()

            if result is None:
                raise Exception("Database query returned no results")

        latency_ms = (time.time() - start_time) * 1000

        return {
            "healthy": True,
            "type": db_type,
            "latency_ms": round(latency_ms, 2),
            "error": None,
        }

    except Exception as e:
        log.error(f"Database health check failed: {e}")
        return {
            "healthy": False,
            "type": db_type,
            "latency_ms": None,
            "error": str(e),
        }


def check_cache() -> dict:
    """
    Check cache (Redis) connectivity.

    Returns:
        dict with keys: healthy (bool), enabled (bool), error (str|None)
    """
    if not settings.redis_enabled:
        return {
            "healthy": True,
            "enabled": False,
            "error": None,
        }

    try:
        # Try to import redis and check connectivity
        import redis

        # Parse Redis URL
        r = redis.from_url(settings.redis_url, decode_responses=True)

        # Test with ping
        r.ping()

        return {
            "healthy": True,
            "enabled": True,
            "error": None,
        }

    except ImportError:
        # Redis not installed - treat as disabled
        return {
            "healthy": True,
            "enabled": False,
            "error": "Redis client not installed",
        }

    except Exception as e:
        log.error(f"Cache health check failed: {e}")
        return {
            "healthy": False,
            "enabled": True,
            "error": str(e),
        }


@router.get("/health/db")
def database_health():
    """
    Detailed database health check endpoint.

    Returns comprehensive database status including:
    - Connection status
    - Latency
    - Database type
    - Basic table verification

    Returns 200 OK if database is healthy, 503 if unhealthy.
    """
    db_info = check_database()

    if not db_info["healthy"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=db_info,
        )

    # Additional checks: verify key tables exist
    try:
        with get_db() as conn:
            cur = get_cursor(conn)

            # Check if users table exists
            if USE_SQLITE:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            else:
                cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')")

            result = cur.fetchone()
            tables_exist = bool(result)

        db_info["tables_verified"] = tables_exist
        db_info["timestamp"] = datetime.utcnow().isoformat()

        return db_info

    except Exception as e:
        log.error(f"Table verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": f"Table verification failed: {str(e)}"},
        )
