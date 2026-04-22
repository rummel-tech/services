"""Artemis Platform API — central hub for all Artemis modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from artemis.core.monitor import start_monitoring, stop_monitoring
from artemis.core.rate_limit import limiter
from artemis.core.registry import registry
from artemis.core.settings import get_settings
from artemis.routers.agent import router as agent_router
from artemis.routers.briefing import router as briefing_router
from artemis.routers.dashboard import router as dashboard_router
from artemis.routers.memory import router as memory_router
from artemis.routers.evolution import router as evolution_router
from artemis.routers.modules import router as modules_router
from artemis.routers.monitor import router as monitor_router
from artemis.routers.multimodal import router as multimodal_router
from artemis.routers.research import router as research_router
from artemis.routers.synthesis import router as synthesis_router
from artemis.routers.workers import router as workers_router

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
    on_startup=[registry.initialize, init_jobs_table, start_monitoring],
    on_shutdown=[registry.shutdown, stop_monitoring],
)

app = create_app(config)

# Wire slowapi limiter for AI endpoints (production-enforced; permissive in dev/test)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(modules_router, prefix=config.api_prefix)
app.include_router(dashboard_router, prefix=config.api_prefix)
app.include_router(agent_router, prefix=config.api_prefix)
app.include_router(briefing_router, prefix=config.api_prefix)
app.include_router(memory_router, prefix=config.api_prefix)
app.include_router(synthesis_router, prefix=config.api_prefix)
app.include_router(workers_router, prefix=config.api_prefix)
app.include_router(monitor_router, prefix=config.api_prefix)
app.include_router(research_router, prefix=config.api_prefix)
app.include_router(evolution_router, prefix=config.api_prefix)
app.include_router(multimodal_router, prefix=config.api_prefix)
