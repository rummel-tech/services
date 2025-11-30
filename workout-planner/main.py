from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ai_engine import AIFitnessEngine
from dotenv import load_dotenv
from pathlib import Path
import os
import time
import sqlite3

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import redis
    from redis.exceptions import RedisError
except ImportError:
    redis = None
    RedisError = None

from aws_secrets import inject_secrets_from_aws
from settings import get_settings, validate_settings
from database import get_db, init_pg_pool, close_pg_pool
from logging_config import init_logging, set_correlation_id, get_logger, correlation_id_var
from error_handlers import install_error_handlers
import metrics
import uuid
from routers import goals, health, strength, swim, murph, readiness, chat, auth, weekly_plans, daily_plans, meals, waitlist
from redis_client import get_redis, is_redis_available
from cache import get_cache_stats
import traceback
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables: default .env, then centralized config/secrets/local.env if present
def _load_env():
    try:
        # Load from current working dir .env (non-overriding)
        load_dotenv(override=False)
        # If SECRETS_ENV_PATH is set, load that file (overrides)
        custom_path = os.environ.get("SECRETS_ENV_PATH")
        if custom_path:
            secrets_env = Path(custom_path)
        else:
            # Default: repo root config/secrets/local.env (overrides)
            repo_root = Path(__file__).resolve().parents[3]
            secrets_env = repo_root / "config" / "secrets" / "local.env"
        if secrets_env.exists():
            load_dotenv(dotenv_path=secrets_env, override=True)
    except Exception:
        # Non-fatal if dotenv not available or file missing
        pass

_load_env()
inject_secrets_from_aws()

settings = validate_settings()
init_logging()

app = FastAPI(
    debug=settings.debug,
    title="Fitness AI API",
    version="1.0.0",
    on_startup=[init_pg_pool],
    on_shutdown=[close_pg_pool],
)

engine = AIFitnessEngine()
log = get_logger("app")
install_error_handlers(app)

# Configure rate limiting (disabled in development for testing)
if settings.environment == "production":
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    # Use a very high limit for dev/test to avoid interference
    limiter = Limiter(key_func=get_remote_address, default_limits=["10000 per minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Middleware for security headers
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    # Add security headers to all responses
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Only add HSTS in production (requires HTTPS)
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Basic Content Security Policy
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"

    return response

# Middleware for request logging & correlation id
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    cid = set_correlation_id()
    start_perf = metrics.start_timer()
    metrics.REQUESTS_IN_PROGRESS.labels(method=request.method, path=request.url.path).inc()
    get_logger("app.request").info("request_start", extra={"path": request.url.path, "method": request.method})
    try:
        response = await call_next(request)
    except Exception as e:
        metrics.record_error("unhandled_exception")
        get_logger("app.request").error(
            "request_error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
    finally:
        metrics.REQUESTS_IN_PROGRESS.labels(method=request.method, path=request.url.path).dec()
    route_obj = request.scope.get("route")
    path_template = route_obj.path if route_obj else request.url.path
    duration_ms = int((time.time() - start_perf) * 1000)
    get_logger("app.request").info(
        "request_end",
        extra={
            "path": path_template,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    metrics.observe_request(request.method, path_template, response.status_code, start_perf)
    response.headers["X-Request-ID"] = cid
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.environment != "development" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(goals.router)
app.include_router(health.router)
app.include_router(strength.router)
app.include_router(swim.router)
app.include_router(murph.router)
app.include_router(readiness.router)
app.include_router(chat.router)
app.include_router(weekly_plans.router)
app.include_router(daily_plans.router)
app.include_router(meals.router)
app.include_router(waitlist.router)

# Root endpoint
@app.get("/")
def root():
    """API root endpoint with service information"""
    return {
        "service": "Workout Planner API",
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.environment,
        "endpoints": {
            "health": "/health",
            "readiness": "/ready",
            "metrics": "/metrics",
            "cache_stats": "/cache/stats",
            "documentation": "/docs",
            "openapi_spec": "/openapi.json"
        },
        "features": [
            "Authentication & JWT tokens",
            "Health metrics tracking",
            "Workout planning (daily & weekly)",
            "Nutrition planning",
            "Readiness scoring",
            "AI-powered recommendations",
            "Prometheus monitoring",
            "Response caching"
        ]
    }

class UserData(BaseModel):
    hrv: float | None = None
    sleep_hours: float | None = None
    resting_hr: float | None = None

class WorkoutData(BaseModel):
    distance_m: float | None = None
    time_s: float | None = None
    weight: float | None = None
    reps: int | None = None
    run1_s: float | None = None
    calis_s: float | None = None
    run2_s: float | None = None

@app.post("/daily")
def daily_plan(user: UserData):
    return engine.generate_daily_plan(user.dict())

@app.post("/weekly")
def weekly_plan(user: UserData):
    return engine.generate_weekly_plan(user.dict())

@app.post("/process/swim")
def swim_metrics(workout: WorkoutData):
    return engine.process_swim_metrics(workout.dict())

@app.post("/process/strength")
def strength_metrics(workout: WorkoutData):
    return engine.process_strength_metrics(workout.dict())

@app.post("/process/murph")
def murph_metrics(workout: WorkoutData):
    return engine.process_murph(workout.dict())

# Basic health endpoints (will expand later)
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def readiness():
    db_ok = False
    redis_ok = False

    # Check database
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            db_ok = True
    except Exception as e:
        is_db_error = isinstance(e, sqlite3.Error) or (psycopg2 and isinstance(e, psycopg2.Error))
        if is_db_error:
            log.warning("readiness_db_failed", extra={"error": str(e), "error_type": type(e).__name__})
        else:
            log.error("readiness_db_unexpected_error", extra={"error": str(e), "error_type": type(e).__name__})
        db_ok = False

    # Check Redis
    try:
        if settings.redis_enabled:
            redis_client = get_redis()
            if redis_client and redis_client.ping():
                redis_ok = True
            else:
                log.warning("readiness_redis_failed", extra={"error": "ping_failed_or_client_none"})
                redis_ok = False
        else:
            redis_ok = None  # Disabled, not an error
    except Exception as e:
        is_redis_error = RedisError and isinstance(e, RedisError)
        if is_redis_error:
            log.warning("readiness_redis_failed", extra={"error": str(e), "error_type": type(e).__name__})
        else:
            log.error("readiness_redis_unexpected_error", extra={"error": str(e), "error_type": type(e).__name__})
        redis_ok = False

    # Determine overall status
    if db_ok:
        if redis_ok is False and settings.redis_enabled:
            status = "degraded"  # Redis expected but failed
        else:
            status = "ready"
    else:
        status = "degraded"  # Database is critical

    return {
        "status": status,
        "environment": settings.environment,
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok is True else ("disabled" if redis_ok is None else "error")
    }

@app.get("/metrics")
def metrics_endpoint():
    data, content_type = metrics.metrics_response()
    return Response(content=data, media_type=content_type)

@app.get("/cache/stats")
def cache_stats():
    """Get cache performance statistics."""
    return get_cache_stats()
