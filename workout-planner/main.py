"""
Workout Planner API - AI-powered fitness coaching service.

This module creates the FastAPI application using the common library factory,
while keeping workout-planner-specific routers and domain logic.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables before any other imports
def _load_env():
    """Load environment variables from .env files."""
    import os
    try:
        load_dotenv(override=False)
        custom_path = os.environ.get("SECRETS_ENV_PATH")
        if custom_path:
            secrets_env = Path(custom_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            secrets_env = repo_root / "config" / "secrets" / "local.env"
        if secrets_env.exists():
            load_dotenv(dotenv_path=secrets_env, override=True)
    except Exception:
        pass

_load_env()

# Import and inject AWS secrets before settings validation
from common.aws_secrets import inject_secrets_from_aws
inject_secrets_from_aws()

# Now import everything else
from common import create_app, ServiceConfig
from core.settings import get_settings
from core.database import init_pg_pool, close_pg_pool
from models.ai_engine import AIFitnessEngine
from routers import (
    goals, health, strength, swim, murph, readiness,
    chat, auth, weekly_plans, daily_plans, meals, waitlist, workouts, healthcheck
)

# Get settings
settings = get_settings()

# Create the service configuration
config = ServiceConfig(
    name="workout-planner",
    title="Fitness AI API",
    version="1.0.0",
    description="AI-powered fitness coaching API with personalized workout planning, readiness scoring, and health integration",
    port=settings.port,
    environment=settings.environment,
    debug=settings.debug,
    log_level=settings.log_level,
    cors_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    enable_security_headers=True,
    enable_request_logging=True,
    enable_error_handlers=True,
    enable_metrics=True,
    enable_rate_limiting=(settings.environment == "production"),
    redis_enabled=settings.redis_enabled,
    redis_url=settings.redis_url,
    on_startup=[init_pg_pool],
    on_shutdown=[close_pg_pool],
)

# Create the app using the common factory
app = create_app(config)

# Initialize the AI engine
engine = AIFitnessEngine()

# Include domain-specific routers
app.include_router(healthcheck.router)  # Health checks first
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
app.include_router(workouts.router)


# Domain-specific request/response models
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


# Legacy AI engine endpoints (kept for backward compatibility)
@app.post("/daily", tags=["AI Engine"])
def daily_plan(user: UserData):
    """Generate a daily workout plan based on user health data."""
    return engine.generate_daily_plan(user.dict())


@app.post("/weekly", tags=["AI Engine"])
def weekly_plan(user: UserData):
    """Generate a weekly workout plan based on user health data."""
    return engine.generate_weekly_plan(user.dict())


@app.post("/process/swim", tags=["AI Engine"])
def swim_metrics(workout: WorkoutData):
    """Process swimming workout metrics."""
    return engine.process_swim_metrics(workout.dict())


@app.post("/process/strength", tags=["AI Engine"])
def strength_metrics(workout: WorkoutData):
    """Process strength workout metrics."""
    return engine.process_strength_metrics(workout.dict())


@app.post("/process/murph", tags=["AI Engine"])
def murph_metrics(workout: WorkoutData):
    """Process Murph workout metrics."""
    return engine.process_murph(workout.dict())
