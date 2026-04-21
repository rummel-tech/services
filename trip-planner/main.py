import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.app_factory import create_app, ServiceConfig
from core.settings import get_settings
from core.database import init_db, init_pg_pool, close_pg_pool, USE_SQLITE

settings = get_settings()


def _on_startup():
    init_db()


config = ServiceConfig(
    name="trip-planner",
    title="Trip Planner API",
    version="0.1.0",
    port=settings.port,
    environment=settings.environment,
    debug=settings.debug,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_metrics=True,
    enable_security_headers=True,
    redis_enabled=settings.redis_enabled,
    on_startup=[_on_startup] if USE_SQLITE else [init_pg_pool],
    on_shutdown=[] if USE_SQLITE else [close_pg_pool],
)

app = create_app(config)

from routers import healthcheck, trips, itinerary, packing, expenses, artemis

app.include_router(healthcheck.router, prefix=config.versioned_prefix)
app.include_router(trips.router, prefix=config.versioned_prefix)
app.include_router(itinerary.router, prefix=config.versioned_prefix)
app.include_router(packing.router, prefix=config.versioned_prefix)
app.include_router(expenses.router, prefix=config.versioned_prefix)
app.include_router(artemis.router, prefix=config.versioned_prefix)
# Legacy routes (backward compat — not shown in OpenAPI docs)
app.include_router(healthcheck.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(trips.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(itinerary.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(packing.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(expenses.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(artemis.router, prefix=config.api_prefix, include_in_schema=False)
