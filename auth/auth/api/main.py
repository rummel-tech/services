"""FastAPI application for the Artemis Auth service."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from auth.core.database import close_db, init_db
from auth.core.jwt_service import get_public_key_pem, init_keys
from auth.core.redis_client import close_redis, configure_redis, init_redis
from auth.core.settings import get_settings
from auth.routers.auth import limiter, router as auth_router
from auth.routers.google import router as google_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_keys()
    init_db()
    if settings.redis_enabled:
        configure_redis(settings.redis_url)
        init_redis()
    yield
    close_db()
    if settings.redis_enabled:
        close_redis()


app = FastAPI(
    title="Artemis Auth Service",
    description="Central authentication service for the Artemis Personal OS platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(google_router)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "artemis-auth",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/auth/public-key")
async def public_key():
    """Return the RSA public key in PEM format.

    Modules call this endpoint once on startup to verify Artemis tokens
    without needing the private key or any shared secret.
    """
    return {"public_key": get_public_key_pem(), "algorithm": "RS256"}
