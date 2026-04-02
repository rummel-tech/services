"""FastAPI application for the Artemis Auth service."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from auth.core.database import close_db, init_db
from auth.core.jwt_service import get_public_key_pem, init_keys
from auth.core.redis_client import close_redis, configure_redis, init_redis
from auth.core.settings import get_settings
from auth.routers.auth import limiter, router as auth_router
from auth.routers.google import router as google_router

from common import create_app, ServiceConfig

settings = get_settings()


def _startup():
    init_keys()
    init_db()
    if settings.redis_enabled:
        configure_redis(settings.redis_url)
        init_redis()


def _shutdown():
    close_db()
    if settings.redis_enabled:
        close_redis()


config = ServiceConfig(
    name="artemis-auth",
    title="Artemis Auth Service",
    version="1.0.0",
    description="Central authentication service for the Artemis Personal OS platform",
    port=settings.port,
    environment=settings.environment,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_metrics=True,
    enable_rate_limiting=False,
    redis_enabled=False,
    on_startup=[_startup],
    on_shutdown=[_shutdown],
)

app = create_app(config)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

public_key_router = APIRouter()


@public_key_router.get("/auth/public-key")
async def public_key():
    """Return the RSA public key in PEM format.

    Modules call this endpoint once on startup to verify Artemis tokens
    without needing the private key or any shared secret.
    """
    return {"public_key": get_public_key_pem(), "algorithm": "RS256"}


app.include_router(auth_router, prefix=config.api_prefix)
app.include_router(google_router, prefix=config.api_prefix)
app.include_router(public_key_router, prefix=config.api_prefix)
app.include_router(public_key_router)
