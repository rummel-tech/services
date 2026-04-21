"""
Work Planner API — Task management, project tracking, and work session planning.

Implements the Artemis Module Contract v1.0 and runs as a standalone service.
Port: 8040
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_env() -> None:
    import os
    try:
        load_dotenv(override=False)
        custom_path = os.environ.get('SECRETS_ENV_PATH')
        if custom_path:
            secrets_env = Path(custom_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            secrets_env = repo_root / 'config' / 'secrets' / 'local.env'
        if secrets_env.exists():
            load_dotenv(dotenv_path=secrets_env, override=True)
    except Exception:
        pass


_load_env()

from common.aws_secrets import inject_secrets_from_aws
inject_secrets_from_aws()

from common import create_app, ServiceConfig
from core.settings import get_settings
from core.database import init_pg_pool, close_pg_pool
from routers import healthcheck, auth, goals, plans, planners, artemis

settings = get_settings()

config = ServiceConfig(
    name='work-planner',
    title='Work Planner API',
    version='0.1.0',
    description='Task management, project tracking, and work session planning',
    port=settings.port,
    environment=settings.environment,
    debug=settings.debug,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_security_headers=True,
    enable_request_logging=True,
    enable_error_handlers=True,
    enable_metrics=True,
    enable_rate_limiting=(settings.environment == 'production'),
    redis_enabled=settings.redis_enabled,
    redis_url=settings.redis_url,
    on_startup=[init_pg_pool],
    on_shutdown=[close_pg_pool],
)

app = create_app(config)

app.include_router(healthcheck.router, prefix=config.versioned_prefix)
app.include_router(auth.router, prefix=config.versioned_prefix)
app.include_router(goals.router, prefix=config.versioned_prefix)
app.include_router(plans.router, prefix=config.versioned_prefix)
app.include_router(planners.router, prefix=config.versioned_prefix)
app.include_router(artemis.router, prefix=config.versioned_prefix)
# Legacy routes (backward compat — not shown in OpenAPI docs)
app.include_router(healthcheck.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(auth.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(goals.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(plans.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(planners.router, prefix=config.api_prefix, include_in_schema=False)
app.include_router(artemis.router, prefix=config.api_prefix, include_in_schema=False)
