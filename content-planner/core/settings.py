from functools import lru_cache
from typing import List, Union

from pydantic_settings import SettingsConfigDict

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.settings import BaseServiceSettings


class ContentPlannerSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "content-planner"
    port: int = 8060
    database_url: str = "sqlite:///content_dev.db"
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/4"
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8060",
    ]

    artemis_auth_url: str = "http://localhost:8090"


@lru_cache()
def get_settings() -> ContentPlannerSettings:
    return ContentPlannerSettings()
