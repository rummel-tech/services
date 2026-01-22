"""Settings and configuration for Artemis service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceURLs(BaseSettings):
    """Backend service URLs configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8"
    )

    home_manager_url: str = "http://localhost:8020"
    vehicle_manager_url: str = "http://localhost:8030"
    meal_planner_url: str = "http://localhost:8010"
    workout_planner_url: str = "http://localhost:8040"


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # Service URLs
    services: ServiceURLs = ServiceURLs()

    # Default user ID for demo purposes
    # In production, this would come from authentication
    default_user_id: str = "demo_user"


# Global settings instance
settings = Settings()
