"""Artemis Platform API — central hub for all Artemis modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from artemis.core.registry import registry
from artemis.core.settings import get_settings
from artemis.routers.agent import router as agent_router
from artemis.routers.dashboard import router as dashboard_router
from artemis.routers.modules import router as modules_router

from common import create_app, ServiceConfig
from common.tasks import init_jobs_table

settings = get_settings()

config = ServiceConfig(
    name="artemis",
    title="Artemis Personal OS Platform",
    version="1.0.0",
    description="Central hub that orchestrates Artemis-compatible modules",
    port=settings.port,
    environment=settings.environment,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_metrics=True,
    enable_rate_limiting=(settings.environment == "production"),
    redis_enabled=False,
    on_startup=[registry.initialize, init_jobs_table],
    on_shutdown=[registry.shutdown],
)

app = create_app(config)

app.include_router(modules_router, prefix=config.api_prefix)
app.include_router(dashboard_router, prefix=config.api_prefix)
app.include_router(agent_router, prefix=config.api_prefix)
