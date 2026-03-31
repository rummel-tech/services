"""Meal Planner specific settings."""

import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Union

from pydantic_settings import SettingsConfigDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.settings import BaseServiceSettings


class MealPlannerSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'meal-planner'
    port: int = 8010

    database_url: str = 'sqlite:///meal_dev.db'

    redis_enabled: bool = False
    redis_url: str = 'redis://localhost:6379/1'

    cors_origins: Union[List[str], str] = ['*']


@lru_cache()
def get_settings() -> MealPlannerSettings:
    return MealPlannerSettings()
