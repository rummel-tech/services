"""Settings for the Artemis Auth service."""
import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Union

from pydantic_settings import SettingsConfigDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from common.settings import BaseServiceSettings


class AuthSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "artemis-auth"
    port: int = 8090

    database_url: str = "sqlite:///auth_dev.db"

    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/1"

    # RSA key paths (dev) or PEM strings (prod via env vars)
    private_key_path: str = "keys/private.pem"
    public_key_path: str = "keys/public.pem"
    private_key_pem: str = ""   # Set in prod — overrides file
    public_key_pem: str = ""    # Set in prod — overrides file

    # Token expiry
    access_token_expire_minutes: int = 60 * 24   # 24h
    refresh_token_expire_days: int = 30

    # Google OAuth — client verifies on device, backend validates ID token
    google_client_id: str = ""

    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
    ]


@lru_cache()
def get_settings() -> AuthSettings:
    return AuthSettings()
