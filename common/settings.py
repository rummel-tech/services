"""
Base settings configuration for all services.

Each service can extend BaseServiceSettings with service-specific fields.
"""

import os
from functools import lru_cache
from typing import List, Union, Optional, Type, TypeVar
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


T = TypeVar("T", bound="BaseServiceSettings")


class BaseServiceSettings(BaseSettings):
    """
    Base settings class for all services.

    Services should subclass this and add their own fields:

        class MyServiceSettings(BaseServiceSettings):
            model_config = SettingsConfigDict(env_prefix="MY_SERVICE_")
            custom_field: str = "default"
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application context
    app_name: str = "service"
    app_context: str = ""  # Optional context path (e.g., "/api/v1")

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Environment
    environment: str = "development"  # development | staging | production
    debug: bool = False
    log_level: str = "info"

    # CORS
    cors_origins: Union[List[str], str] = ["*"]

    # Database (optional - services can override)
    database_url: str = ""

    # Redis (optional)
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    # JWT (optional - for services with auth)
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_exp_minutes: int = 60
    disable_auth: bool = True

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
        # Enforce non-SQLite for production if database is configured
        if not v:
            return v
        env = info.data.get("environment", "development")
        if env == "production" and v.startswith("sqlite"):
            raise ValueError("Production environment must not use SQLite. Provide a Postgres DATABASE_URL.")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _warn_default_secret(cls, v: str, info) -> str:
        env = info.data.get("environment", "development")
        disable_auth = info.data.get("disable_auth", True)
        # Only require JWT secret if auth is enabled in production
        if env == "production" and not disable_auth and v == "CHANGE_ME_IN_PRODUCTION":
            raise ValueError("jwt_secret must be set for production when auth is enabled.")
        return v

    @field_validator("disable_auth")
    @classmethod
    def _prevent_disable_auth_in_prod(cls, v: bool, info) -> bool:
        env = info.data.get("environment", "development")
        if env == "production" and v:
            raise ValueError("Authentication cannot be disabled in production.")
        return v


# Settings cache - services should use get_settings() with their settings class
_settings_cache: dict = {}


def get_settings(settings_class: Type[T] = BaseServiceSettings) -> T:
    """
    Get cached settings instance.

    Usage:
        # For base settings
        settings = get_settings()

        # For custom settings class
        settings = get_settings(MyServiceSettings)
    """
    class_name = settings_class.__name__
    if class_name not in _settings_cache:
        _settings_cache[class_name] = settings_class()
    return _settings_cache[class_name]


def clear_settings_cache():
    """Clear settings cache (useful for testing)."""
    _settings_cache.clear()
