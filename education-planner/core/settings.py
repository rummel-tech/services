"""Education Planner specific settings."""

import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.settings import BaseServiceSettings


class EducationPlannerSettings(BaseServiceSettings):
    """Settings specific to the Education Planner service."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'education-planner'
    port: int = 8050

    database_url: str = 'sqlite:///education_dev.db'

    redis_enabled: bool = False
    redis_url: str = 'redis://localhost:6379/5'

    cors_origins: Union[List[str], str] = [
        'http://localhost:3000',
        'http://localhost:8080',
        'http://localhost:8081',
        'http://127.0.0.1:8080',
    ]

    @field_validator('database_url')
    @classmethod
    def _validate_db(cls, v: str, info) -> str:
        env = info.data.get('environment', 'development')
        if env == 'production' and v.startswith('sqlite'):
            raise ValueError('Production environment must not use SQLite.')
        return v


@lru_cache()
def get_settings() -> EducationPlannerSettings:
    return EducationPlannerSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
