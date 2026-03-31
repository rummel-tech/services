"""Vehicle Manager specific settings."""

import sys
from pathlib import Path
from functools import lru_cache
from typing import List, Union

from pydantic_settings import SettingsConfigDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.settings import BaseServiceSettings


class VehicleManagerSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'vehicle-manager'
    port: int = 8030

    database_url: str = 'sqlite:///vehicle_dev.db'

    redis_enabled: bool = False
    redis_url: str = 'redis://localhost:6379/3'

    cors_origins: Union[List[str], str] = ['*']


@lru_cache()
def get_settings() -> VehicleManagerSettings:
    return VehicleManagerSettings()
