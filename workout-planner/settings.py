from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields like DB_PASSWORD (used by Docker Compose)
    )

    # Application context
    app_name: str = "workout-planner"
    app_context: str = ""  # Optional context path (e.g., "/api/v1")

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    environment: str = "development"  # development | staging | production
    debug: bool = False
    disable_auth: bool = False  # Set to True to bypass authentication in development
    database_url: str = "sqlite:///fitness_dev.db"
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_exp_minutes: int = 60
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
    ]
    log_level: str = "info"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    @field_validator("environment")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.lower()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("database_url")
    @classmethod
    def _validate_db(cls, v: str, info) -> str:
        # Enforce non-SQLite for production
        env = info.data.get("environment", "development")
        if env == "production" and v.startswith("sqlite"):
            raise ValueError("Production environment must not use SQLite. Provide a Postgres DATABASE_URL.")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _warn_default_secret(cls, v: str, info) -> str:
        env = info.data.get("environment", "development")
        if env == "production" and v == "CHANGE_ME_IN_PRODUCTION":
            raise ValueError("jwt_secret must be set for production and cannot use default placeholder.")
        return v

    @field_validator("disable_auth")
    @classmethod
    def _prevent_disable_auth_in_prod(cls, v: bool, info) -> bool:
        env = info.data.get("environment", "development")
        if env == "production" and v:
            raise ValueError("Authentication cannot be disabled in production.")
        return v


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


def validate_settings():
    s = get_settings()
    # Add any additional runtime checks if needed
    return s
