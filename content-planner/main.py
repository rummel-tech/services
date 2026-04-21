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
    name="content-planner",
    title="Content Planner API",
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

from routers import healthcheck, pillars, sources, content_items, queue, sessions, summaries, user_settings, artemis, playlists

app.include_router(healthcheck.router, prefix=config.versioned_prefix)
app.include_router(pillars.router, prefix=config.versioned_prefix)
app.include_router(sources.router, prefix=config.versioned_prefix)
app.include_router(content_items.router, prefix=config.versioned_prefix)
app.include_router(queue.router, prefix=config.versioned_prefix)
app.include_router(sessions.router, prefix=config.versioned_prefix)
app.include_router(summaries.router, prefix=config.versioned_prefix)
app.include_router(user_settings.router, prefix=config.versioned_prefix)
app.include_router(artemis.router, prefix=config.versioned_prefix)
app.include_router(playlists.router, prefix=config.versioned_prefix)
# Legacy routes (backward compat — not shown in OpenAPI docs)
app.include_router(healthcheck.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(pillars.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(sources.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(content_items.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(queue.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(sessions.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(summaries.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(user_settings.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(artemis.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(playlists.router, prefix=config.api_prefix, include_in_schema=False)
