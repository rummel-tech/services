"""
Workout Planner specific settings.

Extends the common BaseServiceSettings with workout-planner-specific fields.
"""

import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

# Add common package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.settings import BaseServiceSettings


class WorkoutPlannerSettings(BaseServiceSettings):
    """Settings specific to the Workout Planner service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Override defaults for this service
    app_name: str = "workout-planner"
    port: int = 8000

    # Database (required for this service)
    database_url: str = "sqlite:///fitness_dev.db"

    # Redis (enabled by default for this service)
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"

    # CORS origins for this service
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
    ]

    @field_validator("database_url")
    @classmethod
    def _validate_db(cls, v: str, info) -> str:
        # Enforce non-SQLite for production
        env = info.data.get("environment", "development")
        if env == "production" and v.startswith("sqlite"):
            raise ValueError("Production environment must not use SQLite. Provide a Postgres DATABASE_URL.")
        return v


@lru_cache()
def get_settings() -> WorkoutPlannerSettings:
    """Get cached settings instance."""
    return WorkoutPlannerSettings()


def validate_settings() -> WorkoutPlannerSettings:
    """Validate and return settings."""
    return get_settings()


def clear_settings_cache():
    """Clear settings cache (for testing)."""
    get_settings.cache_clear()
