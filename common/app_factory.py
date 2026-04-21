"""
Factory for creating standardized FastAPI applications.

Provides production-ready features:
- Structured JSON logging
- Security headers
- CORS configuration
- Prometheus metrics
- Health/readiness endpoints
- Rate limiting (optional)
- Redis caching (optional)
- AWS secrets injection
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .error_handlers import install_error_handlers
from .logging_config import init_logging, set_correlation_id, get_logger
from . import metrics as metrics_module
from . import redis_client


@dataclass
class ServiceConfig:
    """Configuration for a service."""

    # Required
    name: str
    title: str

    # Optional with defaults
    version: str = "0.1.0"
    description: str = ""
    port: int = 8000
    root_path: Optional[str] = None

    # Route prefix for ALB path-based routing (e.g., "/meal-planner")
    api_prefix: str = ""

    # API version string (e.g., "v1"). Routes are registered at both
    # {api_prefix}/{api_version}/... (versioned) and {api_prefix}/... (legacy).
    api_version: str = "v1"

    # Environment
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "info")
    )

    # CORS
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    # Feature flags
    enable_security_headers: bool = True
    enable_request_logging: bool = True
    enable_error_handlers: bool = True
    enable_metrics: bool = True
    enable_rate_limiting: bool = False

    # Redis (optional)
    redis_enabled: bool = field(
        default_factory=lambda: os.getenv("REDIS_ENABLED", "false").lower() == "true"
    )
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    # Lifecycle hooks
    on_startup: List[Callable] = field(default_factory=list)
    on_shutdown: List[Callable] = field(default_factory=list)

    @property
    def versioned_prefix(self) -> str:
        """Full prefix for versioned routes: e.g. '/workout-planner/v1'."""
        if self.api_version:
            return f"{self.api_prefix}/{self.api_version}"
        return self.api_prefix

    def __post_init__(self):
        # Allow root_path override from environment
        env_root_path = os.getenv("ROOT_PATH", "")
        if env_root_path:
            self.root_path = env_root_path

        # Allow api_prefix override from environment
        env_prefix = os.getenv("API_PREFIX", "")
        if env_prefix and not self.api_prefix:
            self.api_prefix = env_prefix

        # Allow metrics to be disabled via env var (useful in tests to avoid
        # Prometheus "Duplicated timeseries" errors when app is imported multiple times)
        if os.getenv("ENABLE_METRICS", "").lower() == "false":
            self.enable_metrics = False

        # Parse CORS origins from environment if set
        env_cors = os.getenv("CORS_ORIGINS", "")
        if env_cors:
            self.cors_origins = [o.strip() for o in env_cors.split(",")]


def create_app(config: ServiceConfig) -> FastAPI:
    """
    Create a FastAPI application with standard configuration.

    Features:
    - Structured JSON logging
    - Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
    - CORS middleware
    - Request correlation IDs
    - Health and readiness endpoints
    - Prometheus metrics endpoint (optional)
    - Rate limiting (optional)

    Args:
        config: Service configuration

    Returns:
        Configured FastAPI application
    """
    # Initialize logging
    init_logging(
        app_name=config.name,
        environment=config.environment,
        log_level=config.log_level
    )
    log = get_logger("app")

    # Initialize metrics if enabled
    if config.enable_metrics:
        # Convert service name to valid metric prefix
        metrics_prefix = config.name.replace("-", "_")
        metrics_module.init_metrics(metrics_prefix)

    # Configure Redis if enabled
    if config.redis_enabled:
        redis_client.configure_redis(
            enabled=True,
            url=config.redis_url
        )

    # Create FastAPI app
    app = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
        root_path=config.root_path or "",
        debug=config.debug,
    )

    # Security headers middleware
    if config.enable_security_headers:
        @app.middleware("http")
        async def security_headers_middleware(request: Request, call_next):
            response = await call_next(request)

            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
            )

            if config.environment == "production":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )

            return response

    # Request logging and correlation ID middleware
    if config.enable_request_logging:
        @app.middleware("http")
        async def request_logging_middleware(request: Request, call_next):
            import time

            # Set correlation ID
            cid = set_correlation_id(request.headers.get("X-Request-ID"))

            # Track request metrics
            start_time = time.time()
            if config.enable_metrics:
                metrics_module.inc_requests_in_progress(
                    request.method, request.url.path
                )

            log.info("request_start", extra={
                "path": request.url.path,
                "method": request.method
            })

            try:
                response = await call_next(request)
            except Exception as e:
                if config.enable_metrics:
                    metrics_module.record_error("unhandled_exception")
                log.error("request_error", extra={
                    "path": request.url.path,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                raise
            finally:
                if config.enable_metrics:
                    metrics_module.dec_requests_in_progress(
                        request.method, request.url.path
                    )

            # Log completion and record metrics
            duration_ms = int((time.time() - start_time) * 1000)
            route = request.scope.get("route")
            path_template = route.path if route else request.url.path

            log.info("request_end", extra={
                "path": path_template,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms
            })

            if config.enable_metrics:
                metrics_module.observe_request(
                    request.method, path_template,
                    response.status_code, start_time
                )

            response.headers["X-Request-ID"] = cid
            response.headers["X-Response-Time-Ms"] = str(duration_ms)

            return response

    # CORS middleware (added last, executes first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            config.cors_origins
            if config.environment != "development"
            else ["*"]
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    if config.enable_error_handlers:
        install_error_handlers(app)

    # Rate limiting (optional)
    if config.enable_rate_limiting:
        try:
            from slowapi import Limiter, _rate_limit_exceeded_handler
            from slowapi.util import get_remote_address
            from slowapi.errors import RateLimitExceeded

            if config.environment == "production":
                limiter = Limiter(key_func=get_remote_address)
            else:
                # High limit for dev/test
                limiter = Limiter(
                    key_func=get_remote_address,
                    default_limits=["10000 per minute"]
                )

            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        except ImportError:
            log.warning("slowapi not installed, rate limiting disabled")

    # Lifecycle events
    @app.on_event("startup")
    async def startup():
        log.info(f"Starting {config.name} ({config.environment})")

        # Initialize Redis if enabled
        if config.redis_enabled:
            redis_client.init_redis()

        # Run custom startup hooks
        for hook in config.on_startup:
            if callable(hook):
                try:
                    result = hook()
                    if hasattr(result, '__await__'):
                        await result
                except Exception as exc:
                    log.error(
                        "startup_hook_failed",
                        extra={"hook": getattr(hook, "__name__", repr(hook)), "error": str(exc)},
                    )
                    raise

    @app.on_event("shutdown")
    async def shutdown():
        log.info(f"Shutting down {config.name}")

        # Close Redis
        if config.redis_enabled:
            redis_client.close_redis()

        # Run custom shutdown hooks
        for hook in config.on_shutdown:
            if callable(hook):
                result = hook()
                if hasattr(result, '__await__'):
                    await result

    # --- Built-in endpoint handlers ---

    async def _health():
        return {"status": "ok", "service": config.name}

    async def _ready():
        ready_status = "ready"
        redis_status = "disabled"
        if config.redis_enabled:
            if redis_client.is_redis_available():
                redis_status = "ok"
            else:
                redis_status = "error"
                ready_status = "degraded"
        return {
            "status": ready_status,
            "service": config.name,
            "environment": config.environment,
            "redis": redis_status,
        }

    async def _metrics_endpoint():
        data, content_type = metrics_module.metrics_response()
        return Response(content=data, media_type=content_type)

    async def _root():
        prefix = config.api_prefix
        endpoints = {
            "health": f"{prefix}/health",
            "readiness": f"{prefix}/ready",
            "documentation": "/docs",
            "openapi_spec": "/openapi.json",
        }
        if config.enable_metrics:
            endpoints["metrics"] = f"{prefix}/metrics"
        if config.redis_enabled:
            endpoints["cache_stats"] = f"{prefix}/cache/stats"
        return {
            "service": config.name,
            "title": config.title,
            "version": config.version,
            "status": "operational",
            "environment": config.environment,
            "endpoints": endpoints,
        }

    # Root-level health endpoints (for ECS target group and container health checks)
    app.get("/health", tags=["Health"])(_health)
    app.get("/ready", tags=["Health"])(_ready)

    # Prefixed endpoints (for ALB path-based routing)
    if config.api_prefix:
        prefixed = APIRouter(prefix=config.api_prefix)
        prefixed.get("/health", tags=["Health"])(_health)
        prefixed.get("/ready", tags=["Health"])(_ready)
        prefixed.get("/", tags=["Root"])(_root)

        if config.enable_metrics:
            prefixed.get("/metrics", tags=["Monitoring"])(_metrics_endpoint)

        if config.redis_enabled:
            from . import cache
            @prefixed.get("/cache/stats", tags=["Monitoring"])
            async def _cache_stats_prefixed():
                return cache.get_cache_stats()

        app.include_router(prefixed)

    # Unprefixed metrics + root (for local dev / direct access)
    if config.enable_metrics:
        app.get("/metrics", tags=["Monitoring"])(_metrics_endpoint)

    if config.redis_enabled:
        from . import cache
        @app.get("/cache/stats", tags=["Monitoring"])
        async def cache_stats():
            return cache.get_cache_stats()

    app.get("/", tags=["Root"])(_root)

    return app
