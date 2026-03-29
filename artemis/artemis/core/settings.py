"""Settings for the Artemis platform service."""
from functools import lru_cache
from pathlib import Path
from typing import List, Union

from pydantic_settings import BaseSettings, SettingsConfigDict


class ArtemisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "artemis"
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "development"
    log_level: str = "info"
    debug: bool = False

    # Auth service
    artemis_auth_url: str = "http://localhost:8090"

    # Module config file (relative to CWD or absolute)
    modules_config: str = "config/modules.yaml"

    # Registry refresh interval in seconds (0 = no background refresh)
    registry_refresh_seconds: int = 300

    # Claude API key for the AI agent
    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-4-6"

    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
    ]


@lru_cache()
def get_settings() -> ArtemisSettings:
    return ArtemisSettings()
