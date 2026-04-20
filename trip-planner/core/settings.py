from functools import lru_cache
from typing import List, Union

from pydantic_settings import SettingsConfigDict

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.settings import BaseServiceSettings


class TripPlannerSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "trip-planner"
    port: int = 8070
    database_url: str = "sqlite:///trip_dev.db"
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/5"
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8070",
    ]

    artemis_auth_url: str = "http://localhost:8090"


@lru_cache()
def get_settings() -> TripPlannerSettings:
    return TripPlannerSettings()
